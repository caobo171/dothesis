"""One JSON-mode call to gpt-5.6-luna, with cost and 429 backoff.

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

DEFAULT_MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 16000
TIMEOUT_S = 900          # a 2,400-word Vietnamese post with reasoning is slow, not stuck
MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 2.0
MAX_RETRY_AFTER_S = 120  # honour Retry-After, but never park a worker for an hour


def price_in() -> float:
    return float(os.getenv("BLOG_LLM_PRICE_IN", "0.20"))  # USD per 1M input tokens


def price_out() -> float:
    return float(os.getenv("BLOG_LLM_PRICE_OUT", "1.20"))  # USD per 1M output tokens


def usd_for(prompt_tokens: int, output_tokens: int) -> float:
    return (prompt_tokens * price_in() + output_tokens * price_out()) / 1_000_000


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    output_tokens: int = 0        # visible + reasoning, because both are billed as output
    reasoning_tokens: int = 0
    seconds: float = 0.0
    truncated: bool = False

    @property
    def usd(self) -> float:
        return usd_for(self.prompt_tokens, self.output_tokens)


class LunaClient:
    """The writer's model. `complete_json(prompt) -> Completion`."""

    def __init__(self, model: str | None = None, client=None, max_attempts: int = MAX_ATTEMPTS,
                 sleep=time.sleep):
        self.model = model or os.getenv("BLOG_LLM_MODEL") or DEFAULT_MODEL
        self.reasoning_effort = (os.getenv("BLOG_REASONING_EFFORT") or "low").strip() or None
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # noqa: PLC0415 — never on qa.py's import path

            key = os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not set, the writer cannot run")
            # max_retries=0: the retry loop below is ours, because it has to
            # honour Retry-After and report the wait in the batch log.
            self._client = OpenAI(api_key=key, timeout=TIMEOUT_S, max_retries=0)
        return self._client

    def complete_json(self, prompt: str) -> Completion:
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
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
        )


def _is_retryable(exc: Exception) -> bool:
    """429 and transport blips retry; a 400 on the prompt never will."""
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    name = type(exc).__name__
    return name in ("APIConnectionError", "APITimeoutError", "InternalServerError",
                    "RateLimitError", "ConnectError", "ReadTimeout")


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
