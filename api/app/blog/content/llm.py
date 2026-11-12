"""One JSON-mode call to gpt-6-luna (or a Claude id via ANTHROPIC_API_KEY), with cost and 429 backoff.

Forty lines of `openai` rather than a dependency on `engine.utils.openai_adapter`:
the API layer imports neither `engine` nor `agent` today and the spec keeps it
that way, so the writer stays runnable from a checkout that only has `api/`.

The gpt-5.6-* constraints are the same ones `engine/utils/openai_adapter.py`
documents, mirrored here because they are 400 errors, not preferences:

  * a non-default `temperature` is rejected, so it is never sent
  * `max_tokens` is rejected, `max_completion_tokens` is the parameter
  * `response_format=json_object` is refused unless the prompt says "json"
  * reasoning tokens are billed as output and are reported separately under
    `usage.completion_tokens_details.reasoning_tokens`
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass

DEFAULT_MODEL = "gpt-6-luna"
# A claude-* model id (BLOG_LLM_MODEL, or the default on a Claude-only deploy)
# routes the writer to the Anthropic API with ANTHROPIC_API_KEY instead.
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"
# Per-1M list prices for the defaults above, so a cost estimate follows the model
# actually configured instead of always quoting luna. BLOG_LLM_PRICE_IN/OUT still
# override, for any other model id.
_DEFAULT_PRICES = {DEFAULT_MODEL: (0.10, 0.50), DEFAULT_CLAUDE_MODEL: (1.00, 5.00)}


def default_model() -> str:
    """BLOG_LLM_MODEL, else the route's default. Follows ORCHESTRATOR_LLM_ROUTE so
    one env line moves the blog writer onto Claude with everything else — a
    Claude-only box has no OPENAI_API_KEY for luna."""
    explicit = (os.getenv("BLOG_LLM_MODEL") or "").strip()
    if explicit:
        return explicit
    if (os.getenv("ORCHESTRATOR_LLM_ROUTE") or "").strip().lower() == "anthropic":
        return DEFAULT_CLAUDE_MODEL
    return DEFAULT_MODEL


def is_claude(model: str) -> bool:
    return (model or "").startswith("claude")
# Reasoning tokens count against this ceiling on gpt-5.6-*, so it bounds the
# model's thinking and its visible answer together. Measured 2026-09-09: at
# 16,000 the ten longest Vietnamese posts (2,560 to 3,802 words) came back as
# summaries at 0.37 to 0.57 of their source length, against a median of 0.84
# across the other 969, and repeating the call reproduced it. Everything that
# fit shipped faithfully, so the ceiling was the whole defect. 32,000 matches
# what `engine/utils/openai_adapter.py` gives a chapter draft, and a ceiling
# costs nothing until it is used.
MAX_OUTPUT_TOKENS = 32000


def max_output_tokens() -> int:
    """The ceiling, overridable per run with BLOG_MAX_OUTPUT_TOKENS.

    A handful of the longest posts still truncate at 32,000 because reasoning
    and answer share the budget, and raising the default for all thousand of
    them to serve five would spend thinking on posts that never needed it.
    """
    raw = (os.getenv("BLOG_MAX_OUTPUT_TOKENS") or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else MAX_OUTPUT_TOKENS
TIMEOUT_S = 900          # a 2,400-word Vietnamese post with reasoning is slow, not stuck
MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 2.0
MAX_RETRY_AFTER_S = 120  # honour Retry-After, but never park a worker for an hour


def _default_price(model: str | None, idx: int) -> float:
    m = model or default_model()
    if m in _DEFAULT_PRICES:
        return _DEFAULT_PRICES[m][idx]
    # Unknown id: Claude ids estimate at Haiku, everything else at luna — an
    # estimate that is wrong by model tier beats one wrong by provider.
    return _DEFAULT_PRICES[DEFAULT_CLAUDE_MODEL if is_claude(m) else DEFAULT_MODEL][idx]


def price_in(model: str | None = None) -> float:
    raw = os.getenv("BLOG_LLM_PRICE_IN")  # USD per 1M input tokens
    return float(raw) if raw else _default_price(model, 0)


def price_out(model: str | None = None) -> float:
    raw = os.getenv("BLOG_LLM_PRICE_OUT")  # USD per 1M output tokens
    return float(raw) if raw else _default_price(model, 1)


def usd_for(prompt_tokens: int, output_tokens: int, model: str | None = None) -> float:
    return (prompt_tokens * price_in(model) + output_tokens * price_out(model)) / 1_000_000


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    output_tokens: int = 0        # visible + reasoning, because both are billed as output
    reasoning_tokens: int = 0
    seconds: float = 0.0
    truncated: bool = False
    model: str | None = None      # priced per model, so a Claude run is not costed at luna rates

    @property
    def usd(self) -> float:
        return usd_for(self.prompt_tokens, self.output_tokens, self.model)


class LunaClient:
    """The writer's model. `complete_json(prompt) -> Completion`."""

    def __init__(self, model: str | None = None, client=None, max_attempts: int = MAX_ATTEMPTS,
                 sleep=time.sleep):
        self.model = model or default_model()
        self.reasoning_effort = (os.getenv("BLOG_REASONING_EFFORT") or "low").strip() or None
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if is_claude(self.model):
                import anthropic  # noqa: PLC0415 — never on qa.py's import path

                key = os.getenv("ANTHROPIC_API_KEY", "")
                if not key:
                    raise RuntimeError("ANTHROPIC_API_KEY is not set, the writer cannot run on Claude")
                # max_retries=0 for the same reason as the OpenAI client below.
                self._client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, max_retries=0)
                return self._client
            from openai import OpenAI  # noqa: PLC0415 — never on qa.py's import path

            key = os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not set, the writer cannot run")
            # max_retries=0: the retry loop below is ours, because it has to
            # honour Retry-After and report the wait in the batch log.
            self._client = OpenAI(api_key=key, timeout=TIMEOUT_S, max_retries=0)
        return self._client

    def complete_json(self, prompt: str) -> Completion:
        if is_claude(self.model):
            return self._complete_json_claude(prompt)
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": max_output_tokens(),
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort

        started = time.time()
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                completion = self.client.chat.completions.create(**request)
                break
            except Exception as exc:  # noqa: BLE001 — retry policy is by shape, not by class
                last_error = exc
                if attempt == self.max_attempts or not _is_retryable(exc):
                    raise
                self._sleep(_wait_seconds(exc, attempt))
        else:  # pragma: no cover - the loop always breaks or raises
            raise last_error

        choice = completion.choices[0]
        usage = getattr(completion, "usage", None)
        reasoning = 0
        prompt_tokens = output_tokens = 0
        if usage is not None:
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = int(getattr(details, "reasoning_tokens", 0) or 0) if details else 0
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return Completion(
            text=choice.message.content or "",
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning,
            seconds=time.time() - started,
            truncated=getattr(choice, "finish_reason", None) == "length",
            model=self.model,
        )

    def _complete_json_claude(self, prompt: str) -> Completion:
        """Same contract as the OpenAI path, over the Anthropic Messages API.

        Claude has no json_object mode, so JSON is asked for in the system prompt
        and a stray ```json fence is stripped. Streamed because a 32K max_tokens
        is past the SDK's non-streaming ceiling (it raises before sending).
        BLOG_REASONING_EFFORT is not sent: Haiku 4.5 has no effort parameter.
        """
        request = {
            "model": self.model,
            "max_tokens": max_output_tokens(),
            "system": "Respond with a single valid JSON object only — no prose and no markdown code fences.",
            "messages": [{"role": "user", "content": prompt}],
        }
        started = time.time()
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self.client.messages.stream(**request) as stream:
                    message = stream.get_final_message()
                break
            except Exception as exc:  # noqa: BLE001 — retry policy is by shape, not by class
                last_error = exc
                if attempt == self.max_attempts or not _is_retryable(exc):
                    raise
                self._sleep(_wait_seconds(exc, attempt))
        else:  # pragma: no cover - the loop always breaks or raises
            raise last_error

        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rstrip().removesuffix("```").strip()
        u = message.usage
        return Completion(
            text=text,
            # input_tokens excludes cache reads/writes on Anthropic; sum them so
            # prompt_tokens means what it does on the OpenAI path.
            prompt_tokens=(int(u.input_tokens or 0)
                           + int(getattr(u, "cache_read_input_tokens", 0) or 0)
                           + int(getattr(u, "cache_creation_input_tokens", 0) or 0)),
            output_tokens=int(u.output_tokens or 0),
            seconds=time.time() - started,
            truncated=message.stop_reason == "max_tokens",
            model=self.model,
        )


def _is_retryable(exc: Exception) -> bool:
    """429 and transport blips retry; a 400 on the prompt never will."""
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None)
    # 529 is Anthropic's "overloaded" — transient, same class as a 503.
    if status in (408, 409, 429, 500, 502, 503, 504, 529):
        return True
    name = type(exc).__name__
    return name in ("APIConnectionError", "APITimeoutError", "InternalServerError",
                    "RateLimitError", "ConnectError", "ReadTimeout", "OverloadedError")


def _wait_seconds(exc: Exception, attempt: int) -> float:
    """Retry-After when the server sent one, exponential backoff otherwise."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw:
        try:
            return min(float(raw), MAX_RETRY_AFTER_S)
        except (TypeError, ValueError):
            pass
    # Jitter, so six workers that hit the same 429 do not all wake together.
    return min(BACKOFF_BASE_S * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_RETRY_AFTER_S)
