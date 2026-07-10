"""Provider abstraction for the central brain. One factory, two routes.

Why this exists: adding/swapping a provider used to mean editing a branch inside
runtime._default_model(). This makes it config, not code — `make_model()` reads a
ModelSpec (from env by default) and returns the right BaseChatModel:

- native      keeps the provider's own SDK so prompt-caching on the big system
              prompt + skills is preserved (the reason native stays the default).
- openrouter  (Task 2) routes through an OpenAI-compatible client with a `models`
              fallback cascade + a no-train/no-log data policy.

Back-compat contract: with no new env, spec_from_env() + make_model() build the
exact same client runtime._default_model() built before F10 — byte-for-byte at
default settings (Gemini gets temperature only; Anthropic gets max_tokens only),
so this is a true drop-in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ModelSpec:
    route: str = "native"  # "native" | "openrouter"
    model: str = "gemini-3.5-flash"
    fallbacks: list[str] = field(default_factory=list)
    temperature: float = 0.4
    max_tokens: int = 8000


def spec_from_env() -> ModelSpec:
    """Read the model spec from env, defaulting to today's native Gemini setup.

    The model default mirrors runtime._default_model(): Claude when an
    ANTHROPIC_API_KEY is configured on the native route, else gemini-3.5-flash.
    DOTHESIS_AGENT_MODEL still overrides, exactly as before.
    """
    route = os.getenv("DOTHESIS_MODEL_ROUTE", "native")
    # Claude is the architecture's preferred model and takes over automatically
    # once a key lands; until then Gemini is the working default.
    default_model = "gemini-3.5-flash"
    if route == "native" and os.getenv("ANTHROPIC_API_KEY"):
        default_model = "claude-sonnet-4-6"
    return ModelSpec(
        route=route,
        model=os.getenv("DOTHESIS_AGENT_MODEL", default_model),
        fallbacks=[m for m in os.getenv("DOTHESIS_MODEL_FALLBACKS", "").split(",") if m.strip()],
        temperature=float(os.getenv("DOTHESIS_MODEL_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("DOTHESIS_MODEL_MAX_TOKENS", "8000")),
    )


def make_model(spec: ModelSpec | None = None):
    """Build the chat model for `spec` (env-derived when omitted).

    Fail fast: an unknown route raises here, at build time, rather than mid-turn.
    """
    spec = spec or spec_from_env()
    if spec.route == "native":
        return _native(spec)
    if spec.route == "openrouter":
        return _openrouter(spec)  # Task 2
    raise ValueError(f"unknown model route: {spec.route!r}")


def _native(spec: ModelSpec):
    # Native SDKs keep provider prompt-caching for the big system prompt + skills.
    # Construction MUST match runtime._default_model() at default settings:
    #   - Anthropic: model + max_tokens, NO temperature kwarg.
    #   - Gemini:    model + temperature, NO max_tokens kwarg.
    if os.getenv("ANTHROPIC_API_KEY") and "claude" in spec.model:
        from langchain_anthropic import ChatAnthropic  # noqa: PLC0415 — lazy, heavy dep

        return ChatAnthropic(model=spec.model, max_tokens=spec.max_tokens)
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415 — lazy, heavy dep

    return ChatGoogleGenerativeAI(model=spec.model, temperature=spec.temperature)


def _openrouter(spec: ModelSpec):
    """OpenAI-compatible client pointed at OpenRouter: fallback cascade + data policy.

    The key check runs BEFORE the (lazy) langchain_openai import so a misconfigured
    route fails fast with a clear message even where the eval-only dep isn't
    installed — and never mid-turn. langchain_openai stays lazy because the native
    route (the default) must not require it.
    """
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("openrouter route needs OPENROUTER_API_KEY (set it or use route=native)")
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — openrouter-only, lazy

    models = [spec.model, *spec.fallbacks]
    return ChatOpenAI(
        model=spec.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        # OpenRouter-specific: fallback cascade + no-train/no-log provider filter.
        # data_collection=deny is the default so student PII is never used for
        # training; override via DOTHESIS_OPENROUTER_DATA_POLICY only deliberately.
        extra_body={
            "models": models,
            "provider": {
                "data_collection": os.getenv("DOTHESIS_OPENROUTER_DATA_POLICY", "deny"),
                "allow_fallbacks": True,
            },
        },
        # OpenAI-compatible streaming reports usage only when asked — the credit
        # ledger reads it via extract_usage, so keep this on.
        model_kwargs={"stream_options": {"include_usage": True}},
    )
