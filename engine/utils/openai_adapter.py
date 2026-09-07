"""
ABOUTME: OpenAI-compatible chat model behind the engine's Gemini-shaped generate_content() interface.
ABOUTME: Lets the draft agents run on gpt-5.6-luna (OpenAI direct) or an Ofox-prefixed id without touching callers.

Every draft agent goes through run_agent(model, ...) and reads the response
like the google-genai SDK returns it: .text, .candidates[0].content.parts,
.candidates[0].finish_reason and .usage_metadata. This adapter produces that
shape from /v1/chat/completions, so switching the pipeline from Gemini 3.1 Pro
($2 / $12 per 1M tokens) to Luna ($0.20 / $1.20) is a model-id change, not a
code change.

Known gpt-5.6-* constraints, mirrored from agent/model_factory._openai:
  - `temperature` other than the default is rejected (400) → never sent
  - `max_tokens` is rejected → `max_completion_tokens` is used
  - the model reasons by default; reasoning tokens are billed as output and are
    reported here as usage_metadata.thoughts_token_count
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

try:
    from .gemini_cache import llm_cache_enabled, cache_get, cache_put, make_key, TTL_LLM
    from .gemini_client import CachedResponse, _store_response
except ImportError:  # script-style import with engine/utils on sys.path
    from gemini_cache import llm_cache_enabled, cache_get, cache_put, make_key, TTL_LLM
    from gemini_client import CachedResponse, _store_response

OFOX_BASE_URL = "https://api.ofox.ai/v1"
DEFAULT_MAX_OUTPUT_TOKENS = 32768   # a chapter draft is ≤ ~15k tokens; leave room for reasoning
DEFAULT_TIMEOUT_S = 900


@dataclass
class _Part:
    text: str
    thought: bool = False
    function_call: Optional[object] = None


@dataclass
class _Content:
    parts: List[_Part]
    role: str = "model"


@dataclass
class _Candidate:
    content: _Content
    finish_reason: str = "STOP"


@dataclass
class _Usage:
    prompt_token_count: int = 0
    candidates_token_count: int = 0
    thoughts_token_count: int = 0
    cached_content_token_count: int = 0

    @property
    def total_token_count(self) -> int:
        return self.prompt_token_count + self.candidates_token_count + self.thoughts_token_count


@dataclass
class ChatResponse:
    """Gemini-shaped view of one chat completion."""
    text: str
    usage_metadata: _Usage
    finish_reason: str = "STOP"
    model: str = ""
    candidates: List[_Candidate] = field(default_factory=list)
    function_calls: Optional[list] = None

    def __post_init__(self):
        if not self.candidates:
            self.candidates = [_Candidate(content=_Content(parts=[_Part(text=self.text)]),
                                          finish_reason=self.finish_reason)]


@dataclass
class _TokenCount:
    total_tokens: int


class OpenAIChatModel:
    """Drop-in for GeminiModelWrapper backed by an OpenAI-compatible endpoint."""

    def __init__(
        self,
        model_name: str,
        route: str = "openai",
        max_output_tokens: Optional[int] = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ):
        try:
            from openai import OpenAI  # lazy: the Gemini route must not need this dep
        except ImportError as e:
            raise ImportError("openai package required for non-Gemini draft models: pip install openai") from e

        self.route = route
        if route == "ofox":
            key = os.getenv("OFOX_API_KEY", "")
            if not key:
                raise ValueError("DRAFT_LLM_ROUTE=ofox needs OFOX_API_KEY")
            # Ofox wants provider-prefixed ids (openai/gpt-5.6-luna)
            self.model_name = model_name if "/" in model_name else f"openai/{model_name}"
            self.client = OpenAI(api_key=key, base_url=OFOX_BASE_URL, timeout=timeout_s, max_retries=3)
        else:
            key = os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise ValueError(
                    "OPENAI_API_KEY not found. Set it, or run the draft engine on Gemini with "
                    "DRAFT_LLM_ROUTE=native (DRAFT_MODEL=gemini-3.1-pro-preview)."
                )
            self.model_name = model_name
            self.client = OpenAI(api_key=key, timeout=timeout_s, max_retries=3)

        self.max_output_tokens = int(
            max_output_tokens or os.getenv("DRAFT_MAX_OUTPUT_TOKENS") or DEFAULT_MAX_OUTPUT_TOKENS
        )
        # Unset → the model's own default. "low"/"medium"/"high"/"none" to override.
        self.reasoning_effort = (os.getenv("DRAFT_REASONING_EFFORT") or "").strip() or None
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
            # temperature deliberately ignored: gpt-5.6-* only accepts the default

        request: dict = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": contents}],
            "max_completion_tokens": max_out,
        }
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        # json_object mode is refused unless the prompt itself mentions JSON
        if want_json and "json" in contents.lower():
            request["response_format"] = {"type": "json_object"}

        cache_key = None
        if llm_cache_enabled():
            cache_key = make_key("llm", self.model_name, contents,
                                 {k: v for k, v in request.items() if k not in ("messages", "model")})
            hit = cache_get("llm", cache_key)
            if hit is not None:
                logger.info("LLM cache hit (%s, %d-char prompt)", self.model_name, len(contents))
                return CachedResponse(hit)

        completion = self.client.chat.completions.create(**request)
        choice = completion.choices[0]
        text = choice.message.content or ""
        finish = "MAX_TOKENS" if choice.finish_reason == "length" else "STOP"

        usage = _Usage()
        if completion.usage is not None:
            u = completion.usage
            reasoning = 0
            details = getattr(u, "completion_tokens_details", None)
            if details is not None:
                reasoning = getattr(details, "reasoning_tokens", 0) or 0
            usage = _Usage(
                prompt_token_count=u.prompt_tokens or 0,
                candidates_token_count=max((u.completion_tokens or 0) - reasoning, 0),
                thoughts_token_count=reasoning,
            )
        if finish == "MAX_TOKENS":
            logger.warning("%s hit max_completion_tokens=%d (reasoning %d, visible %d tokens)",
                           self.model_name, max_out, usage.thoughts_token_count, usage.candidates_token_count)

        response = ChatResponse(text=text, usage_metadata=usage, finish_reason=finish, model=completion.model or self.model_name)
        if cache_key:
            _store_response(cache_key, self.model_name, response)
        return response

    def count_tokens(self, text: str) -> _TokenCount:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("o200k_base")
            return _TokenCount(total_tokens=len(enc.encode(text)))
        except Exception:
            return _TokenCount(total_tokens=max(1, len(text) // 4))
