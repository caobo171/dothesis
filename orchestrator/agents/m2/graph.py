"""M2 sub-graph builder — supervisor in the middle, 5 phase nodes on the spokes."""
from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m2.state import M2SubGraphState, PhaseKey


def _stub_phase(next_phase: PhaseKey):
    # Returns a stub node function that advances to the next phase.
    # Will be replaced by real phase implementations in Tasks 10-14.
    def _node(state: M2SubGraphState) -> dict:
        return {"current_phase": next_phase}
    return _node


_PHASE_TO_NODE_NAME = {
    "familiarize": "m2_familiarize",
    "research_state": "m2_research_state",
    "gap_analysis": "m2_gap_analysis",
    "reference_confirm": "m2_reference_confirm",
    "output_gen": "m2_output_gen",
}


def _route_from_start(state: M2SubGraphState) -> str:
    # Route to the correct phase node based on current_phase, or END if already DONE.
    phase = state.get("current_phase", "familiarize")
    if phase == "DONE":
        return "END"
    return _PHASE_TO_NODE_NAME.get(phase, "m2_familiarize")


def build_m2_subgraph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    builder = StateGraph(M2SubGraphState)
    # Use real `run` if the phase module provides one, otherwise fall back to stubs
    builder.add_node("m2_familiarize", getattr(phase1_familiarize, "run", _stub_phase("research_state")))
    builder.add_node("m2_research_state", getattr(phase2_research_state, "run", _stub_phase("gap_analysis")))
    builder.add_node("m2_gap_analysis", getattr(phase3_gap_analysis, "run", _stub_phase("reference_confirm")))
    builder.add_node("m2_reference_confirm", getattr(phase4_reference_confirm, "run", _stub_phase("output_gen")))
    builder.add_node("m2_output_gen", getattr(phase5_output_gen, "run", _stub_phase("DONE")))

    builder.add_conditional_edges(START, _route_from_start, {
        "m2_familiarize": "m2_familiarize", "m2_research_state": "m2_research_state",
        "m2_gap_analysis": "m2_gap_analysis", "m2_reference_confirm": "m2_reference_confirm",
        "m2_output_gen": "m2_output_gen", "END": END,
    })
    builder.add_edge("m2_familiarize", "m2_research_state")
    builder.add_edge("m2_research_state", "m2_gap_analysis")
    builder.add_edge("m2_gap_analysis", "m2_reference_confirm")
    builder.add_edge("m2_reference_confirm", "m2_output_gen")
    builder.add_edge("m2_output_gen", END)

    # In interactive mode, interrupt before every phase node so the user can review
    interrupt_before = [] if not interactive else [
        "m2_familiarize", "m2_research_state", "m2_gap_analysis",
        "m2_reference_confirm", "m2_output_gen",
    ]
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


@lru_cache(maxsize=2)
def get_m2_graph(interactive: bool = True):
    from orchestrator.graph import _get_pool
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_m2_subgraph(interactive=interactive, checkpointer=saver)
