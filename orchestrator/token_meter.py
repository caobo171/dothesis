"""Brief §1.8 — token meter at the LLM call boundary.

Wraps `orchestrator.agents.base.bounded_invoke` with an estimate → reserve
→ reconcile loop so per-action pricing is grounded in real usage, not in
hand-tuned heuristics on top of unbounded LLM calls.

Persistence: when a project_id is supplied, every metered call appends a
row to the `token_ledger` table (model, action_kind, prompt/completion
tokens, request time). The router/handlers use plain `bounded_invoke`
when project_id is absent (e.g. evals, intake assess) — the meter is
opt-in per call so unit tests don't need the table.

Why a separate module and not inline in base.py: keeps `bounded_invoke`
stable for callers (intake, supervisor, router) that don't want the
ledger overhead. Callers that DO want the meter import `metered_invoke`
explicitly — easier to grep, easier to flag-gate.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from orchestrator.agents.base import bounded_invoke
from orchestrator.llm import resolve_orchestrator_model

logger = logging.getLogger(__name__)


# Rough per-char → token ratio for Gemini Flash. Used ONLY for the pre-call
# `reserved` estimate; reconcile uses the response's true `usage_metadata`.
# 4 chars/token is the standard Gemini approximation and matches Google's
# tokenizer within ~15% on academic English prompts — close enough for a
# reservation that gets reconciled within seconds.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class LedgerEntry:
    """One metered call. Persisted to `token_ledger` (PR #3 migration).

    `delta = consumed - reserved` is what the per-project meter aggregates
    — positive means we under-reserved (cost more than predicted).
    """
    project_id: uuid.UUID | None
    action_kind: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reserved: int
    duration_ms: int


# Pluggable persistence sink. Tests inject a list-collector here; the
# FastAPI app wires it to a SQL writer via `register_sink`. Default no-op
# so an orchestrator process running without the API surface (e.g. evals)
# doesn't need any setup.
_SINK: Callable[[LedgerEntry], None] = lambda _e: None


def get_sink() -> Callable[[LedgerEntry], None]:
    """Current sink, resolved at CALL time.

    Callers must not capture `_SINK` at import time: orchestrator/__main__.py
    installs the real sink after the module graph is already loaded, so a
    captured reference would stay the default no-op and silently drop every row.
    """
    return _SINK


def register_sink(sink: Callable[[LedgerEntry], None]) -> None:
    """Install the persistence writer. Idempotent — last writer wins.

    The API process (api/app/main.py) calls this once on startup to point
    at a SQL writer that INSERTs into `token_ledger`. Unit tests can
    install a list-appending sink to verify what got recorded.
    """
    global _SINK
    _SINK = sink


def estimate_tokens(prompt: Any) -> int:
    """Cheap upper-bound token estimate for the reservation step.

    Operates on the prompt's string form (joined messages, system+human
    concatenated) rather than per-message — Gemini's tokenizer doesn't
    expose a count-only API, and re-tokenizing every prompt to count would
    double the latency. The 4-char/token rule overestimates slightly on
    code/JSON, which is the safe direction for a reservation.
    """
    if isinstance(prompt, list):
        chars = sum(len(getattr(m, "content", str(m))) for m in prompt)
    else:
        chars = len(str(prompt))
    return max(1, chars // _CHARS_PER_TOKEN)


def _usage_from_response(resp: Any) -> tuple[int, int]:
    """Extract (prompt_tokens, completion_tokens) from a LangChain response.

    LangChain normalizes provider metadata into `response.usage_metadata`
    when available. Falls back to (0, 0) on providers that don't surface
    usage (we still record the call so the action's existence is logged).
    """
    usage = getattr(resp, "usage_metadata", None) or {}
    return (
        int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0),
    )


def project_id_from_env() -> uuid.UUID | None:
    """The run's project, as job_runner puts it in the subprocess env.

    job_runner.spawn_orchestrator_run sets PROJECT_ID (job_runner.py:407). Reading
    it here is what lets metering be attached ONCE at client construction instead
    of threading project_id through 20 tool call sites — none of which currently
    take it.
    """
    raw = os.getenv("PROJECT_ID", "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        logger.warning("PROJECT_ID=%r is not a uuid — ledger rows will be unattributed", raw)
        return None


from langchain_core.callbacks import BaseCallbackHandler


class LedgerCallback(BaseCallbackHandler):
    """LangChain callback that writes one ledger row per completed LLM call.

    A CALLBACK rather than a wrapper object around the client, deliberately.
    Tools do not share one call style: 9 modules go through `bounded_invoke`
    while m1_topic, m4_analysis, m4_parsers and intake call `llm.invoke(...)`
    straight, and several then `.bind_tools()` or `.with_structured_output()`.
    A proxy would have to re-wrap every derived client and would silently stop
    metering the ones it missed; callbacks are copied onto derived clients by
    LangChain itself, so they cannot be shed that way.

    Failures here are swallowed: a billing-telemetry bug must never take down a
    student's run. A dropped row under-bills, which is visible in aggregate; a
    raised exception loses the whole draft.

    Subclasses BaseCallbackHandler because the LangChain clients are Pydantic
    models that validate `callbacks` with an isinstance check — a duck-typed
    handler is rejected at construction.
    """

    def __init__(self, action_kind: str, project_id: uuid.UUID | None) -> None:
        super().__init__()
        self.action_kind = action_kind
        self.project_id = project_id
        self._t0: dict[Any, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kw):  # noqa: ANN001
        self._t0[run_id] = time.monotonic()

    on_chat_model_start = on_llm_start

    def on_llm_end(self, response, *, run_id=None, **kw):  # noqa: ANN001
        try:
            t0 = self._t0.pop(run_id, None)
            duration_ms = int((time.monotonic() - t0) * 1000) if t0 else 0
            prompt_tok, completion_tok, model = _usage_from_llm_result(response)
            entry = LedgerEntry(
                project_id=self.project_id,
                action_kind=self.action_kind,
                model=model or resolve_orchestrator_model(),
                prompt_tokens=prompt_tok,
                completion_tokens=completion_tok,
                reserved=0,  # callbacks meter after the fact; no reservation step
                duration_ms=duration_ms,
            )
            _SINK(entry)
        except Exception:  # noqa: BLE001
            logger.exception("LedgerCallback failed for action=%s", self.action_kind)


def _usage_from_llm_result(response: Any) -> tuple[int, int, str | None]:
    """Pull (prompt, completion, model) out of a LangChain LLMResult.

    Checks the message's `usage_metadata` first — the normalised shape both the
    OpenAI and Gemini integrations populate — then falls back to the provider's
    raw `llm_output["token_usage"]`, which is what older integrations set.
    """
    model = None
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        usage = getattr(msg, "usage_metadata", None) or {}
        meta = getattr(msg, "response_metadata", None) or {}
        model = meta.get("model_name") or meta.get("model")
        if usage:
            return (int(usage.get("input_tokens", 0) or 0),
                    int(usage.get("output_tokens", 0) or 0), model)
    except (AttributeError, IndexError, TypeError):
        pass
    out = getattr(response, "llm_output", None) or {}
    tu = out.get("token_usage") or out.get("usage") or {}
    return (
        int(tu.get("prompt_tokens", 0) or tu.get("input_tokens", 0) or 0),
        int(tu.get("completion_tokens", 0) or tu.get("output_tokens", 0) or 0),
        model or out.get("model_name"),
    )


def metered_invoke(
    llm: Any,
    prompt: Any,
    *,
    action_kind: str,
    project_id: uuid.UUID | None = None,
    max_seconds: int = 60,
    retries: int = 1,
):
    """Wrap bounded_invoke with the brief §1.8 meter.

    Args:
        llm:         a LangChain chat model (the same instance you'd pass
                     to bounded_invoke).
        prompt:      messages list or string.
        action_kind: a short identifier for the ledger ("router_pick",
                     "m1_extract_field", "read_slice", …). Aggregated
                     per-kind for the action-pricing table.
        project_id:  ledger row's project. None → no ledger row written,
                     just bounded_invoke pass-through. Useful for evals
                     and one-off calls.
        max_seconds: forwarded to bounded_invoke (wall-clock cap).
        retries:     forwarded to bounded_invoke.

    Returns the LLM response. Raises whatever bounded_invoke raises —
    the meter doesn't swallow errors; if the call failed we still write
    a ledger row marking the failure (zero tokens, real duration).
    """
    # This label is what job_runner BILLS against (it groups ledger rows by model
    # and prices each at its own rate), so a wrong label overcharges — it is not
    # cosmetic. The fallback therefore resolves through the factory's route-aware
    # helper rather than re-guessing an unprefixed native default: on route=ofox
    # that guess labelled qwen-plus runs as gemini-2.5-flash. Prefer the object's
    # real `.model` whenever it exposes one — that's ground truth over any env.
    model = (
        resolve_orchestrator_model()
        if not hasattr(llm, "model") else getattr(llm, "model", "unknown")
    )
    reserved = estimate_tokens(prompt)
    t0 = time.monotonic()
    try:
        resp = bounded_invoke(llm, prompt, max_seconds=max_seconds, retries=retries)
        prompt_tok, completion_tok = _usage_from_response(resp)
        return resp
    except Exception:
        prompt_tok, completion_tok = 0, 0
        raise
    finally:
        # Write the ledger in a finally so exceptions still record the
        # attempt — important for cost forensics ("did we attempt 500 calls
        # at $0 because Gemini was down?" is a question we want to answer).
        duration_ms = int((time.monotonic() - t0) * 1000)
        entry = LedgerEntry(
            project_id=project_id,
            action_kind=action_kind,
            model=str(model),
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            reserved=reserved,
            duration_ms=duration_ms,
        )
        try:
            _SINK(entry)
        except Exception:  # noqa: BLE001
            # Persistence failures must NOT block the user-facing response.
            # A dropped ledger row is recoverable (we'd notice in aggregate
            # cost drift); a thrown exception here breaks every turn.
            logger.exception("token_meter sink failed for action=%s", action_kind)
