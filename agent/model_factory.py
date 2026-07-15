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
    route: str = "native"  # "native" | "openrouter" | "ofox"
    model: str = "gemini-3.5-flash"
    fallbacks: list[str] = field(default_factory=list)
    temperature: float = 0.4
    max_tokens: int = 8000
    # Vision routing (headless convergence spec §2). vision_model "" means
    # "use the default Gemini sidecar" — it picks WHICH Gemini make_vision_model
    # builds, never the family. supports_vision is derived from `model` and
    # FAIL-CLOSED: unknown ids are assumed text-only, because the wrong default
    # ships Gemini media blocks into an OpenAI-compat endpoint and hard-fails,
    # while a needless transcription costs fractions of a cent.
    vision_model: str = ""
    supports_vision: bool = False


# Substring lookup on the model id — the same technique opencode uses for
# prompt selection. A KNOWN MAINTENANCE POINT: new vision-capable families
# must be added here, and fail-closed keeps that drift cheap (spec Risk 4).
_VISION_MODEL_HINTS = ("gemini", "claude")


def model_supports_vision(model: str) -> bool:
    m = (model or "").lower()
    return any(h in m for h in _VISION_MODEL_HINTS)


def spec_from_env() -> ModelSpec:
    """Read the model spec from env, defaulting to today's native Gemini setup.

    The model default mirrors runtime._default_model(): Claude when an
    ANTHROPIC_API_KEY is configured on the native route, else gemini-3.5-flash.
    DOTHESIS_AGENT_MODEL still overrides, exactly as before.
    """
    # DEPLOY CONSTRAINT — the route stays `native` in code, deliberately.
    # _ofox() raises RuntimeError without OFOX_API_KEY, so defaulting to ofox here
    # would break every dev machine and any deploy lacking the key. Moving production
    # onto ofox is a DEPLOYMENT change (DOTHESIS_MODEL_ROUTE=ofox in env); this file
    # only decides WHICH model you get once you are already on ofox.
    #
    # ⚠️ SHIP-TOGETHER: the credit_multiplier correction (f64bf79) must NOT reach
    # production while the live default is still gemini-3.5-flash. Table-derived
    # pricing bills 3.5-flash at ~12.86x, and PACKAGES are sized on "1 pack ≈ 1 run",
    # so a Starter pack would buy ~1/13 of a run and students hit a wall immediately.
    # The env flip to ofox + qwen-plus (~0.62x) and that multiplier change are one
    # deployment, not two.
    route = os.getenv("DOTHESIS_MODEL_ROUTE", "native")
    # Claude is the architecture's preferred model and takes over automatically
    # once a key lands; until then Gemini is the working default.
    default_model = "gemini-3.5-flash"
    if route == "native" and os.getenv("ANTHROPIC_API_KEY"):
        default_model = "claude-sonnet-4-6"
    elif route == "ofox":
        # Ofox uses provider/model ids. qwen-plus (0.12/0.29) is the only default that
        # bills BELOW the credit baseline (gemini-2.5-flash native, 0.15/0.60 → 1.0x by
        # construction): it resolves to ~0.62x. That is load-bearing, not incidental —
        # api/app/pricing.py::PACKAGES are sized on "1 pack ≈ 1 run", so a default above
        # 1.0x silently shrinks what a pack buys.
        #
        # NOT google/gemini-2.5-flash (the previous default): Ofox RESELLS 2.5-flash at
        # 0.30/2.50, not Google's native 0.15/0.60, so it bills ~3.24x — it was never the
        # baseline the old name-matching multiplier assumed it was.
        # Trade-off accepted: qwen-plus is text-only, so image turns go to the Gemini
        # vision sidecar (make_vision_model) instead of the brain. Override via
        # DOTHESIS_AGENT_MODEL.
        default_model = "bailian/qwen-plus"
    model = os.getenv("DOTHESIS_AGENT_MODEL", default_model)
    return ModelSpec(
        route=route,
        model=model,
        fallbacks=[m for m in os.getenv("DOTHESIS_MODEL_FALLBACKS", "").split(",") if m.strip()],
        temperature=float(os.getenv("DOTHESIS_MODEL_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("DOTHESIS_MODEL_MAX_TOKENS", "8000")),
        vision_model=os.getenv("DOTHESIS_VISION_MODEL", ""),
        supports_vision=model_supports_vision(model),
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
    if spec.route == "ofox":
        return _ofox(spec)
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


def _ofox(spec: ModelSpec):
    """OpenAI-compatible client pointed at Ofox (https://api.ofox.ai/v1).

    Ofox is a unified gateway (one key -> Claude/GPT/Gemini/Qwen/DeepSeek/…) at
    ~provider rates, so it's the cost/quality lever: route to a cheaper model
    (e.g. google/gemini-2.5-flash: ~15x cheaper output than 3.5-flash) or a
    stronger/Vietnamese-better one (qwen) without a native SDK per provider.
    Model IDs are `provider/model`, e.g. "google/gemini-2.5-flash".

    CACHING CAVEAT: Ofox documents caching on the provider-NATIVE protocol, not
    this OpenAI-compatible endpoint — so the big system-prompt + skills prefix may
    NOT get the ~90% input cache discount here. That's usually fine because DoThesis
    cost is output-dominated (uncacheable anyway), but verify `cached_*` token
    counts on a real response; if input caching turns out to matter for your model,
    use route=native for that provider instead. Key check runs before the (lazy)
    langchain_openai import so a misconfig fails fast, never mid-turn.
    """
    key = os.getenv("OFOX_API_KEY", "")
    if not key:
        raise RuntimeError("ofox route needs OFOX_API_KEY (set it or use route=native)")
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — gateway-only, lazy

    return ChatOpenAI(
        model=spec.model,  # provider/model, e.g. "google/gemini-2.5-flash"
        base_url="https://api.ofox.ai/v1",
        api_key=key,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        # OpenAI-compatible streaming reports usage only when asked — the credit
        # ledger reads it via extract_usage, so keep this on.
        model_kwargs={"stream_options": {"include_usage": True}},
    )


def make_vision_model(spec: ModelSpec | None = None, temperature: float | None = None):
    """Vision-capable model for image / screenshot / scanned-PDF turns.

    Implementation moved here from orchestrator/llm.get_vision_llm so "what
    model am I on" has ONE source of truth (spec §2 — this takes the
    model-truth sources from three to one and clears the path for D).

    Always a Gemini client: the vision path builds Gemini-format content
    blocks, which the OpenAI-compat Ofox route can't consume. On route=ofox we
    point the Gemini client at Ofox's Gemini-NATIVE endpoint (verified
    working) with the Ofox key; else native Google. temperature defaults 0.2 —
    transcription wants determinism, not creativity.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415 — lazy, heavy dep

    spec = spec or spec_from_env()
    # This is the SIDECAR factory: it exists only for brains that CANNOT see, so
    # it is always Gemini. `vision_model` therefore overrides WHICH Gemini, never
    # the family — "" just means "the default sidecar". Resolving "" to
    # spec.model would hand e.g. a Claude id to the Gemini client below: it
    # constructs fine and fails at invoke. A vision-capable brain never needs
    # this function at all; build_user_message gives it native blocks instead.
    m = spec.vision_model or "gemini-2.5-flash"
    t = 0.2 if temperature is None else temperature
    ofox_key = os.getenv("OFOX_API_KEY")
    if spec.route == "ofox" and ofox_key:
        vm = m if "/" in m else f"google/{m}"  # Ofox needs provider-prefixed ids
        return ChatGoogleGenerativeAI(
            model=vm, google_api_key=ofox_key,
            client_options={"api_endpoint": "https://api.ofox.ai/gemini"},
            transport="rest", temperature=t)
    return ChatGoogleGenerativeAI(model=m, temperature=t)
