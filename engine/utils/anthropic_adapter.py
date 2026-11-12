"""
ABOUTME: Claude chat model behind the engine's Gemini-shaped generate_content() interface.
ABOUTME: Lets the draft agents run on claude-haiku-4-5 (or any Claude id) with an ANTHROPIC_API_KEY.

Sibling of utils/openai_adapter.py, and returns the SAME ChatResponse shape
(.text, .candidates[0].content.parts, .candidates[0].finish_reason,
.usage_metadata) so run_agent() and every draft agent read it unchanged.
Switching the draft engine to Claude is DRAFT_LLM_ROUTE=anthropic (or
inheriting ORCHESTRATOR_LLM_ROUTE=anthropic), not a code change.

Claude differences this adapter absorbs:
  - Always STREAMS. A chapter needs a large max_tokens, and the anthropic SDK
    refuses a non-streaming request whose max_tokens implies >10 min ("Streaming
    is required…"). Streaming + get_final_message() has no such ceiling and the
    caller still gets one complete response.
  - No json_object mode. JSON requests get a system instruction instead, and a
    ```json fence is stripped if the model adds one anyway, so callers that
    json.loads(response.text) keep working.
  - `temperature` is not sent, matching openai_adapter: the draft engine already
    runs at the provider default on luna, and newer Claude tiers 400 on it.
  - input_tokens EXCLUDES cache reads/writes on Anthropic (OpenAI's prompt_tokens
    includes them), so prompt_token_count sums all three to keep the meter's
    "total prompt tokens" meaning identical across adapters.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from .gemini_cache import llm_cache_enabled, cache_get, make_key
    from .gemini_client import CachedResponse, _store_response
    from .openai_adapter import ChatResponse, _Usage, _TokenCount
except ImportError:  # script-style import with engine/utils on sys.path
    from gemini_cache import llm_cache_enabled, cache_get, make_key
    from gemini_client import CachedResponse, _store_response
    from openai_adapter import ChatResponse, _Usage, _TokenCount

DEFAULT_MAX_OUTPUT_TOKENS = 32768   # same chapter budget openai_adapter gives luna; Haiku 4.5 caps at 64K
DEFAULT_TIMEOUT_S = 900

_JSON_SYSTEM = ("Respond with a single valid JSON value only — no prose before or after it, "
                "and no markdown code fences.")


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


class AnthropicChatModel:
    """Drop-in for GeminiModelWrapper backed by the Anthropic Messages API."""

    def __init__(
        self,
        model_name: str,
        max_output_tokens: Optional[int] = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ):
        try:
            import anthropic  # lazy: the Gemini/OpenAI routes must not need this dep
        except ImportError as e:
            raise ImportError("anthropic package required for Claude draft models: pip install anthropic") from e

        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set it, or run the draft engine on another route "
                "with DRAFT_LLM_ROUTE=openai|native."
            )
        self.route = "anthropic"
        self.model_name = model_name
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout_s, max_retries=3)
        self.max_output_tokens = int(
            max_output_tokens or os.getenv("DRAFT_MAX_OUTPUT_TOKENS") or DEFAULT_MAX_OUTPUT_TOKENS
        )
        self.default_temperature = None  # parity with GeminiModelWrapper; never sent (see module doc)

    # -- Gemini-compatible surface -------------------------------------------------

    def generate_content(self, prompt: Any, generation_config: Any = None, safety_settings: Any = None) -> Any:
        _ = safety_settings
        if isinstance(prompt, str):
            contents = prompt
        elif isinstance(prompt, list):
            contents = "\n".join(str(p) for p in prompt)
        else:
            contents = str(prompt)

        max_out = self.max_output_tokens
        want_json = False
        if generation_config is not None:
            cfg = generation_config if isinstance(generation_config, dict) else vars(generation_config)
            if cfg.get("max_output_tokens"):
                max_out = int(cfg["max_output_tokens"])
            want_json = (cfg.get("response_mime_type") or "") == "application/json"

        request: dict = {
            "model": self.model_name,
            "max_tokens": max_out,
            "messages": [{"role": "user", "content": contents}],
        }
        if want_json:
            request["system"] = _JSON_SYSTEM

        cache_key = None
        if llm_cache_enabled():
            cache_key = make_key("llm", self.model_name, contents,
                                 {k: v for k, v in request.items() if k not in ("messages", "model")})
            hit = cache_get("llm", cache_key)
            if hit is not None:
                logger.info("LLM cache hit (%s, %d-char prompt)", self.model_name, len(contents))
                return CachedResponse(hit)

        with self.client.messages.stream(**request) as stream:
            message = stream.get_final_message()

        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        if want_json:
            text = _strip_json_fence(text)
        if message.stop_reason == "max_tokens":
            finish = "MAX_TOKENS"
        elif message.stop_reason == "refusal":
            finish = "SAFETY"
        else:
            finish = "STOP"

        u = message.usage
        cached = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        prompt_tokens = (int(u.input_tokens or 0) + cached
                         + int(getattr(u, "cache_creation_input_tokens", 0) or 0))
        usage = _Usage(
            prompt_token_count=prompt_tokens,
            candidates_token_count=int(u.output_tokens or 0),
            cached_content_token_count=cached,
        )
        if finish == "MAX_TOKENS":
            logger.warning("%s hit max_tokens=%d (%d output tokens)",
                           self.model_name, max_out, usage.candidates_token_count)

        response = ChatResponse(text=text, usage_metadata=usage, finish_reason=finish,
                                model=message.model or self.model_name)
        if cache_key:
            _store_response(cache_key, self.model_name, response)
        return response

    def count_tokens(self, text: str) -> _TokenCount:
        # Local estimate, not messages.count_tokens: this is called for budgeting
        # inside loops, and a network round-trip per call is not worth exactness.
        return _TokenCount(total_tokens=max(1, len(text) // 4))
