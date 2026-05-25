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
