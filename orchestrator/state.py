"""Orchestrator state model — in-memory graph state + project-shared context store."""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


ModuleKey = Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
Mode = Literal["interactive", "auto"]
_MODULES: tuple[ModuleKey, ...] = ("M1", "M2", "M3", "M4", "M5")


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
