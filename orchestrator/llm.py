"""Shared LLM factory for the orchestrator ENGINE. One chokepoint, two routes.

Why this exists: the engine built its Gemini model in ~10 copies of a `_get_llm()`
helper, each hardcoding `ChatGoogleGenerativeAI(model=..., temperature=...)`. That
meant swapping the whole engine onto a different provider was a 10-file edit. This
factory makes it config, not code: set ORCHESTRATOR_LLM_ROUTE=ofox and the entire
engine routes through the Ofox gateway — no code change.

This mirrors agent/model_factory.py (the central brain's factory) but is kept
SEPARATE on purpose: importing agent.model_factory here would create an
orchestrator -> agent import cycle, so the tiny Ofox construction is duplicated.

Back-compat contract: with no new env (route=native), get_orchestrator_llm()
builds the exact same client the `_get_llm()` sites built before — Gemini gets
model + temperature and nothing else — so this is a true drop-in.
"""
from __future__ import annotations

import os


def get_orchestrator_llm(model: str | None = None, temperature: float | None = None):
    """Build the engine's chat model for the configured route.

    Args mirror the old per-site construction so callers can preserve their
    tool-specific settings:
      - model:       defaults to ORCHESTRATOR_LLM_MODEL / "gemini-2.5-flash"
                     (the exact default every `_get_llm()` used).
      - temperature: defaults to 0.4 (the modal per-site value); each site
                     passes its own (e.g. m4 analysis uses 0.2).

    Fail fast: an unknown route raises here, at build time, not mid-run.
    """
    route = os.getenv("ORCHESTRATOR_LLM_ROUTE", "native")
    model = model or os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash")
    temperature = 0.4 if temperature is None else temperature

    if route == "native":
        # Native SDK, unchanged construction: Gemini gets model + temperature,
        # NOTHING else (no max_tokens) — byte-for-byte with the old `_get_llm()`
        # sites. Import stays local so this module is import-light.
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    if route == "ofox":
        # OpenAI-compatible client pointed at the Ofox gateway. The key check runs
        # BEFORE the (lazy) langchain_openai import so a misconfigured route fails
        # fast with a clear message even where the gateway-only dep isn't
        # installed — and never mid-run. langchain_openai stays lazy because the
        # native route (the default) must not require it.
        key = os.getenv("OFOX_API_KEY", "")
        if not key:
            raise RuntimeError(
                "ofox route needs OFOX_API_KEY (set it or use ORCHESTRATOR_LLM_ROUTE=native)"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415 — gateway-only, lazy

        return ChatOpenAI(
            model=model,  # provider/model, e.g. "google/gemini-2.5-flash"
            base_url="https://api.ofox.ai/v1",
            api_key=key,
            temperature=temperature,
            # OpenAI-compatible streaming reports usage only when asked — the
            # credit ledger reads it via extract_usage, so keep this on.
            model_kwargs={"stream_options": {"include_usage": True}},
        )

    raise ValueError(f"unknown orchestrator LLM route: {route!r}")
