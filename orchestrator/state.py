"""Orchestrator state model — in-memory graph state + project-shared context store."""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


ModuleKey = Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
Mode = Literal["interactive", "auto"]
_MODULES: tuple[ModuleKey, ...] = ("M1", "M2", "M3", "M4", "M5")

# Brief §1.4 — per-module workflow status (separate from conversation focus).
# Soft lock per §8.4: `locked` is a recommendation, NOT a wall — the router
# and handlers must still respond when a user wanders into a locked module.
ModuleStatus = Literal["locked", "in_progress", "done", "needs_review"]


class ContextStore(BaseModel):
    """Project-shared confirmed module outputs.

    Stored in the `context_store` DB table as JSONB columns. Threads of the same
    project read & write this concurrently — `orchestrator/concurrency.py` enforces
    first-confirm-wins on writes.
    """
    m1_topic: dict | None = None
    m2_literature: dict | None = None
    m3_design: dict | None = None
    m4_analysis: dict | None = None
    m5_writing: dict | None = None
    # Rolling per-module summaries for the tiered memory layer (brief §5).
    # Populated by the async compaction job once FULL_MODE_CEILING is crossed
    # in PR #4. The field ships in PR #1 so the schema is stable before the
    # memory layer lands — avoids a second migration just to add this key.
    # Keys are ModuleKey strings ("M1".."M5"); empty dict = no compaction yet.
    module_summaries: dict[str, str] = Field(default_factory=dict)


class ModuleStatusMap(BaseModel):
    """Per-module workflow status map (brief §1.4).

    Pure-DERIVED state — compute_status_map() rebuilds it from ContextStore on
    every load. We persist it on `projects.module_status` for fast reads (UI
    sidebar, planner heuristics), but ContextStore + the `_needs_review` slice
    marker is the source of truth. NEVER mutate this map directly to change
    state — mutate the slice and recompute.

    Default = all locked, matching an untouched project.
    """
    M1: ModuleStatus = "locked"
    M2: ModuleStatus = "locked"
    M3: ModuleStatus = "locked"
    M4: ModuleStatus = "locked"
    M5: ModuleStatus = "locked"


class OrchestratorState(TypedDict, total=False):
    """LangGraph in-memory state for a single graph invocation."""
    project_id: UUID
    thread_id: UUID
    # add_messages reducer merges incoming messages into the list instead of
    # overwriting — required by LangGraph 1.x for multi-step message accumulation.
    messages: Annotated[list[BaseMessage], add_messages]
    current_module: ModuleKey
    context_store: ContextStore
    mode: Mode
    user_intent: str | None
    pending_confirmations: list[str]
    # Set by each module node to the inverse of ModuleStepResult.transition:
    # True  → the module paused for user input (route the turn to END),
    # False → the module finished/transitioned (route back to supervisor to
    #         advance to the next module within the same turn).
    # This is the UNIVERSAL pause signal. It replaces the old heuristic that
    # sniffed _awaiting_field/_awaiting_confirm out of a module's context slice —
    # that only worked for base-loop modules (M1/M4/M5) and made M2/M3 (which
    # keep their own phase markers) loop supervisor↔module forever.
    _module_paused: bool
    # When set (an artifact key like "analysis"), the supervisor routes via the
    # planner toward this artifact — backfilling missing prerequisites — instead
    # of the sequential rule. Cleared once the target is reached. This is how
    # "enter at any step" drives the graph; None = normal sequential flow.
    target_artifact: str | None
    # Stage-1 router-graph field. The router agent (orchestrator/agents/
    # router_agent.py) records the module-tool it just invoked here so the
    # SSE adapter can stamp the assistant reply with the correct module_tag
    # (the v1 graph used the LangGraph node_name for this, but the v2 graph
    # has only one node — router_agent_node — so the module identity has to
    # ride on state instead). Just a string, msgpack-clean.
    last_tool_called: str | None
    # Structured payload from the most recent rich-widget click (FlowChart,
    # ListEditor, ...). Shape: {"field_name": <schema field>, "value": <any
    # JSON>}. The chat router sets it from the SendMessageBody on every turn
    # the user clicked a widget; ModuleAgent consumes it to bypass LLM
    # text-extraction (lossy for nested shapes — see base.py). None when the
    # user typed free text. Not a reducer field — the chat router overwrites
    # each turn, so stale payloads can't leak between turns.
    pending_widget_payload: dict | None
    # Brief §1.4 — conversation focus, separate from workflow status.
    # During the dual-write window (PR #1) callers fall back to current_module
    # when focus is None; PR #2 makes focus the canonical routing knob and
    # demotes current_module to a shadow. None on cold-start = the router's
    # cold-start short-circuit picks M1.
    focus: ModuleKey | None
    # Brief §1.4 — per-module workflow status. Derived from context_store
    # via compute_status_map; carried on state so the router (PR #2) can
    # set needs_review on downstream modules after a mutate without a
    # second read of the slice. Recompute, don't mutate this map.
    status: ModuleStatusMap
    # NOTE: progress streaming. The chat router stashes the per-request
    # emitter in engine.utils.progress's thread_id registry (NOT graph
    # state) because LangGraph's postgres checkpointer msgpack-serializes
    # state and chokes on Python callables. M2Agent reads thread_id from
    # this state and looks up the emitter via progress.lookup() — keeps
    # state msgpack-clean while the wiring still works end-to-end.


_MODULE_TO_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


def get_module_slice(cs: ContextStore, module: ModuleKey) -> dict:
    """Read the partial schema for the given module. Returns {} if untouched.

    Agents call this instead of touching ContextStore directly so we have a
    single chokepoint for any future access-control or redaction.
    """
    if module == "DONE":
        return {}
    return getattr(cs, _MODULE_TO_FIELD[module]) or {}


def is_module_confirmed(cs: ContextStore, module: ModuleKey) -> bool:
    # A module is confirmed when its slice contains a 'confirmed_at' timestamp.
    if module == "DONE":
        return True
    return bool(get_module_slice(cs, module).get("confirmed_at"))


def next_unconfirmed_module(cs: ContextStore) -> ModuleKey:
    """Walk M1..M5 in order; return the first not-yet-confirmed module, or DONE."""
    for m in _MODULES:
        if not is_module_confirmed(cs, m):
            return m
    return "DONE"


# Meta keys that don't count as module content for status derivation.
# Routing markers (_awaiting_*, _needs_review) and provenance (_source) are
# bookkeeping — a slice carrying ONLY meta keys must stay 'locked' so the
# locked→in_progress transition still fires the moment the user enters real
# content. Anything else starting with "_" is also treated as meta by the
# leading-underscore convention used throughout the codebase.
_META_SLICE_KEYS = frozenset({
    "confirmed_at", "_source", "_awaiting_field",
    "_awaiting_confirm", "_needs_review",
})


def _slice_has_content(slice_: dict) -> bool:
    """True iff the slice carries any non-meta field with a non-empty value.

    None / "" / [] / {} all count as "empty" — they're indistinguishable from
    "field not set" for the user-facing status. This is the in_progress
    detection rule for compute_status_map.
    """
    for k, v in slice_.items():
        if k in _META_SLICE_KEYS or k.startswith("_"):
            continue
        if v in (None, "", [], {}):
            continue
        return True
    return False


def modules_after(target: ModuleKey) -> tuple[ModuleKey, ...]:
    """Strict downstream modules of `target` in M1..M5 order.

    Returns the tuple of module keys that come AFTER target in the canonical
    sequence (so M2's downstream is M3, M4, M5; M5's downstream is empty).
    Used by propagate_needs_review to walk the blast radius of a mutate.

    `target` itself is NOT in its own downstream — brief §1.5 propagates to
    "downstream modules", not to the mutated module (which the user just
    edited; flagging it for review would loop on every edit).
    """
    if target == "DONE":
        return ()
    try:
        idx = _MODULES.index(target)
    except ValueError:
        return ()
    return _MODULES[idx + 1 :]


def propagate_needs_review(cs: ContextStore, *, mutated: ModuleKey) -> ContextStore:
    """Brief §1.5 — flag downstream DONE modules as needs_review after a mutate.

    Returns a NEW ContextStore. Pure function: the input is left intact so the
    router can swap stores atomically in its state patch (avoids hidden mutation
    through cached references — e.g. graph state already in flight).

    Only `done` downstream modules get the marker. in_progress/locked modules
    have nothing committed to invalidate, so flagging them would be noise —
    the user'd see "⚠" on a step they haven't started yet.

    The marker is `_needs_review: True` on the slice itself (single source of
    truth — compute_status_map reads it). Cleared when the user re-confirms
    the module (its agent step() drops the marker on its next write).
    """
    downstream = modules_after(mutated)
    if not downstream:
        return cs

    # Use the current status (BEFORE this mutate's writes — propagation runs
    # against the pre-mutate state) to decide which downstream modules were
    # done. compute_status_map is pure so this is cheap.
    status = compute_status_map(cs)

    # Build the patch dict slice-by-slice. model_copy(update=...) only accepts
    # full slice replacements, so we read-merge-write per affected slice.
    patch: dict[str, dict | None] = {}
    for m in downstream:
        if getattr(status, m) != "done":
            continue
        field = _MODULE_TO_FIELD[m]
        existing = getattr(cs, field) or {}
        patch[field] = {**existing, "_needs_review": True}

    if not patch:
        return cs
    return cs.model_copy(update=patch)


def compute_status_map(cs: ContextStore) -> ModuleStatusMap:
    """Derive the per-module workflow status from a ContextStore (brief §1.4).

    Status semantics (precedence order):
      1. needs_review — slice carries `_needs_review` marker. Set by the
         router (PR #2) when an upstream mutate invalidates this module.
         Wins over `confirmed_at`: a done-but-now-stale module IS the case
         the marker exists for.
      2. done — `confirmed_at` present OR the module's DoD validator passes.
         confirmed_at remains authoritative on top of DoD so a user-approved
         imperfect slice doesn't flap back to in_progress.
      3. in_progress — slice has any non-meta content but isn't done yet.
      4. locked — empty slice. SOFT lock per brief §8.4; the router and
         module handlers must still answer for a locked module.

    Pure function — single source of truth is ContextStore. Callers MUST
    recompute after any context_store write rather than mutating the returned
    ModuleStatusMap directly (mutating it can't change the slice it claims to
    describe).
    """
    # Imported lazily because orchestrator.artifacts imports state.py
    # transitively (via ContextStore in readiness()) — a top-level import
    # would create a cycle.
    from orchestrator.artifacts import (
        dod_analysis, dod_design, dod_literature, dod_topic,
    )

    # M5 splits into per-chapter artifacts (see artifacts.ARTIFACTS), so
    # there's no module-level DoD validator yet — done fires via confirmed_at
    # alone. PR #3 (WizardAgent for M5) adds a module-level dod_writing.
    _dod_by_module = {
        "M1": dod_topic,
        "M2": dod_literature,
        "M3": dod_design,
        "M4": dod_analysis,
    }

    out: dict[str, ModuleStatus] = {}
    for m in _MODULES:
        slice_ = get_module_slice(cs, m)
        if slice_.get("_needs_review"):
            out[m] = "needs_review"
            continue
        confirmed = bool(slice_.get("confirmed_at"))
        dod_done = m in _dod_by_module and _dod_by_module[m](slice_).done
        if confirmed or dod_done:
            out[m] = "done"
        elif _slice_has_content(slice_):
            out[m] = "in_progress"
        else:
            out[m] = "locked"
    return ModuleStatusMap(**out)
