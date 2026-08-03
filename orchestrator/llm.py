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

def resolve_orchestrator_model(model: str | None = None) -> str:
    """Resolve the engine's model id for the configured route. ONE resolution.

    Why this is a function and not an inline getenv default: the route and the
    model must not be settable into an incoherent pair. ORCHESTRATOR_LLM_MODEL used
    to default to the unprefixed native id "gemini-2.5-flash" regardless of route,
    so ORCHESTRATOR_LLM_ROUTE=ofox WITHOUT the model var sent the gateway an id it
    does not serve — the same half-enabled-route shape that billed auto runs 4x
    (job_runner.py:358). Making the DEFAULT route-aware means uncommenting the route
    line alone lands on a coherent model, so a partial config can't fire the bug.

    Mirrors agent/model_factory.spec_from_env() deliberately — same shape (pick a
    default FROM the route, then let the env var override) so the brain and the
    engine stay one mental model rather than two competing patterns.

    Precedence: explicit arg (per-site overrides like ORCHESTRATOR_ROUTER_MODEL)
    > ORCHESTRATOR_LLM_MODEL > the route's default.
    """
    if model:
        return model
    # Default route is `openai` (2026-08-03). It was `native`/gemini-2.5-flash,
    # which stopped describing reality after the 2026-08-02 cutover: every
    # deployment sets ORCHESTRATOR_LLM_ROUTE=openai, so the code default was a
    # fallback nothing used and every reader had to mentally override.
    # Trade-off, stated: _openai() raises without OPENAI_API_KEY, so a machine
    # with no env now fails at model construction instead of quietly landing on
    # Gemini. That is the intended direction — a missing key should be loud.
    route = os.getenv("ORCHESTRATOR_LLM_ROUTE", "openai")
    # native keeps gemini-2.5-flash: the exact id every `_get_llm()` site used, so
    # the no-new-env back-compat contract in this module's header still holds.
    default_model = "gemini-2.5-flash"
    if route == "ofox":
        # Ofox uses provider/model ids. qwen-plus matches the brain's ofox default
        # (agent/model_factory.spec_from_env) and is the model the owner's benchmark
        # picked for the report pipeline — see ARCHITECTURE_NOTES.md.
        default_model = "bailian/qwen-plus"
    if route == "openai":
        # Bare id — OpenAI direct, no provider/ prefix. Matches the brain's
        # openai default (agent.model_factory.spec_from_env) so engine and brain
        # stay on one model, which is the whole point of this function.
        default_model = "gpt-5.6-luna"
    return os.getenv("ORCHESTRATOR_LLM_MODEL", default_model)


def get_orchestrator_llm(
    model: str | None = None,
    temperature: float | None = None,
    timeout: int | None = None,
    route: str | None = None,
    binds_tools: bool = False,
):
    """Build the engine's chat model for the configured route.

    Args mirror the old per-site construction so callers can preserve their
    tool-specific settings:
      - model:       defaults via resolve_orchestrator_model() — ROUTE-AWARE, so
                     route=ofox alone can't leave a native id pointed at the
                     gateway. native still resolves "gemini-2.5-flash", the exact
                     default every `_get_llm()` used.
      - temperature: defaults to 0.4 (the modal per-site value); each site
                     passes its own (e.g. m4 analysis uses 0.2).
      - timeout:     per-request timeout (seconds). Only the hot-path sites set
                     it (base.py, supervisor, router, read, intake, backfill,
                     m2/intent all passed timeout=ORCHESTRATOR_LLM_TIMEOUT so a
                     stalled request can't wedge the whole turn). Default None
                     keeps the timeout-free sites (phase2/phase4) byte-for-byte
                     — no timeout kwarg reaches the client, its default stands.
                     Both langchain clients accept `timeout`, so this is a safe
                     passthrough for either route.

    Fail fast: an unknown route raises here, at build time, not mid-run.

    `route` lets one call site pick a different provider than the global engine
    without touching env — used by the humanize pass to run on Gemini while the
    report writer stays on qwen. None keeps the env default, so every existing
    caller is byte-for-byte unchanged.
    """
    # Same default as resolve_orchestrator_model above — the two MUST agree, or
    # the route picking the client and the route picking the model id diverge
    # and you get a native model id sent to OpenAI.
    route = route or os.getenv("ORCHESTRATOR_LLM_ROUTE", "openai")
    model = resolve_orchestrator_model(model)
    temperature = 0.4 if temperature is None else temperature
    # Metering is attached HERE, at the one place every tool gets its client,
    # rather than at the ~29 call sites — 9 of which use bounded_invoke and the
    # rest call llm.invoke() directly, so there is no single invoke path to hook.
    # Auto runs previously wrote ZERO token_ledger rows (metered_invoke has no
    # production callers), so _charge_auto_run found nothing and billed nothing.
    # project_id comes from the PROJECT_ID env job_runner already sets on the
    # subprocess; outside that process it is None and rows are simply unattributed
    # (chat is billed separately by chat_v3._finalize, so no double-charge).
    #
    # Import is LAZY: token_meter imports orchestrator.agents.base for
    # bounded_invoke, and base.py imports THIS module — a module-level import
    # here is a genuine circular-import crash, not a style preference.
    from orchestrator.token_meter import (  # noqa: PLC0415 — cycle-avoiding
        LedgerCallback, project_id_from_env,
    )
    _cb = [LedgerCallback("orchestrator_llm", project_id_from_env())]

    if route == "native":
        # Native SDK, unchanged construction: Gemini gets model + temperature
        # (+ timeout only when the caller set one) — byte-for-byte with the old
        # `_get_llm()` sites. Import stays local so this module is import-light.
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

        kwargs = {"model": model, "temperature": temperature, "callbacks": _cb}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return ChatGoogleGenerativeAI(**kwargs)

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

        kwargs = {
            "model": model,  # provider/model, e.g. "google/gemini-2.5-flash"
            "base_url": "https://api.ofox.ai/v1",
            "api_key": key,
            "temperature": temperature,
            # OpenAI-compatible streaming reports usage only when asked — the
            # credit ledger reads it via extract_usage, so keep this on.
            "model_kwargs": {"stream_options": {"include_usage": True}},
            "callbacks": _cb,
        }
        # Preserve the hot-path per-request timeout across the gateway too, so
        # the ofox route has the same anti-wedge protection the native sites had.
        if timeout is not None:
            kwargs["timeout"] = timeout
        return ChatOpenAI(**kwargs)

    if route == "openai":
        # OpenAI direct — no gateway. Mirrors agent.model_factory._openai; see
        # that docstring for why Ofox costs 5x for the same model.
        #
        # The `temperature` arg every call site passes is ACCEPTED AND DROPPED
        # here, deliberately. gpt-5.6-* rejects any temperature but the default
        # (400 "Only the default (1) value is supported"), so honouring
        # m4_analysis's 0.2 is impossible on this model — on any route. Dropping
        # it in ONE place keeps all 20 call sites byte-for-byte unchanged rather
        # than spreading route-awareness through the pipeline; switching back to
        # route=ofox or native restores the parameter with no code edits.
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "openai route needs OPENAI_API_KEY (set it or use ORCHESTRATOR_LLM_ROUTE=ofox)"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415 — route-only, lazy

        kwargs = {
            "model": model,  # bare id, e.g. "gpt-5.6-luna"
            "api_key": key,
            # stream_usage, not a raw stream_options in model_kwargs: OpenAI 400s
            # on stream_options for non-streaming requests, and the orchestrator
            # calls invoke() far more than it streams. Same usage numbers for the
            # credit ledger, attached only when streaming.
            "stream_usage": True,
            "callbacks": _cb,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        # Reasoning is disabled ONLY for callers that bind tools.
        #
        # gpt-5.6-* reasons by default and OpenAI 400s on reasoning + function
        # tools over /v1/chat/completions, so the fix is required — but it was
        # first applied to this whole factory, which was too wide. Exactly one
        # orchestrator caller binds tools (router_agent's
        # bind_tools(ALL_TOOLS, tool_choice="any")); everything else here is
        # tool-free prose generation, and humanize is the most quality-sensitive
        # of them. Turning reasoning off for all of them bought nothing and cost
        # output quality on the passes that care most about it.
        if binds_tools:
            kwargs["reasoning_effort"] = "none"
        return ChatOpenAI(**kwargs)

    raise ValueError(f"unknown orchestrator LLM route: {route!r}")


def get_vision_llm(model: str | None = None, temperature: float | None = None):
    """Thin delegate — the implementation moved to agent.model_factory.
    make_vision_model (headless convergence spec §2: one model-truth source).
    Kept so agent/tools/output_parse.py and auto-mode call sites keep working.

    The import is LAZY (inside the function) on purpose: a module-level
    `import agent...` here is exactly the orchestrator -> agent import cycle
    this file's header warns against. Both directions being in-function keeps
    module load acyclic.

    Route resolution preserves this delegate's historical dual-env behavior
    (auto-mode sets ORCHESTRATOR_LLM_ROUTE, chat sets DOTHESIS_MODEL_ROUTE).
    """
    from agent.model_factory import ModelSpec, make_vision_model  # noqa: PLC0415 — cycle-avoiding lazy import

    route = (os.getenv("ORCHESTRATOR_LLM_ROUTE") or os.getenv("DOTHESIS_MODEL_ROUTE") or "native").lower()
    m = model or os.getenv("DOTHESIS_VISION_MODEL", "gemini-2.5-flash")
    return make_vision_model(ModelSpec(route=route, vision_model=m), temperature=temperature)
