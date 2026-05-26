"""M2 sub-graph state — kept separate from outer OrchestratorState.

Sub-graph reads outer state on entry via _seed_from_outer (in translation.py) and
writes back to context_store.m2_literature on exit via _flatten_to_m2_output.
The state below is in-memory only; LangGraph PostgresSaver checkpoints it
under thread_id "{outer}::m2".
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


PhaseKey = Literal[
    "familiarize", "research_state", "gap_analysis",
    "reference_confirm", "output_gen", "DONE",
]


class M2SubGraphState(TypedDict, total=False):
    # --- Inputs from outer state (set on entry) ---
    project_id: UUID | str
    thread_id: UUID | str
    research_title: str
    research_type: Literal["quantitative", "qualitative", "mixed"]
    language: Literal["vi", "en", "bilingual"]
    paper_uris: list[str]
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["interactive", "auto"]

    # --- Phase pointer ---
    current_phase: PhaseKey
    regeneration_count: dict[str, int]

    # --- Phase 1 ---
    has_uploaded_papers: bool | None

    # --- Phase 2 ---
    research_state_draft: str | None
    research_state_refinements: list[str]
    research_state_confirmed: bool
    research_state_citations: list[dict]

    # --- Phase 3 ---
    candidate_gaps: list[dict] | None
    gap_refinements: list[str]
    selected_gap_ids: list[str] | None

    # --- Phase 4 ---
    pending_page_checks: list[dict]
    verified_refs: list[dict]
    page_check_cursor: int

    # --- Phase 5 ---
    ch2_draft: str | None
    citation_list: list[dict]


def fresh_state(
    *,
    project_id, thread_id, research_title: str, research_type: str,
    language: str, paper_uris: list[str], mode: str,
) -> M2SubGraphState:
    """Seed a brand-new sub-graph state for an entry into M2."""
    return {
        "project_id": project_id, "thread_id": thread_id,
        "research_title": research_title, "research_type": research_type,
        "language": language, "paper_uris": list(paper_uris),
        "messages": [], "mode": mode,
        "current_phase": "familiarize",
        "regeneration_count": {},
        "has_uploaded_papers": None,
        "research_state_draft": None,
        "research_state_refinements": [],
        "research_state_confirmed": False,
        "research_state_citations": [],
        "candidate_gaps": None,
        "gap_refinements": [],
        "selected_gap_ids": None,
        "pending_page_checks": [],
        "verified_refs": [],
        "page_check_cursor": 0,
        "ch2_draft": None,
        "citation_list": [],
    }
