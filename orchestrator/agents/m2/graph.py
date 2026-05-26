"""M2 sub-graph builder — conditional edges support self-loops + jump-back."""
from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m2.state import M2SubGraphState, PhaseKey


_PHASE_TO_NODE_NAME: dict[PhaseKey, str] = {
    "familiarize": "m2_familiarize",
    "research_state": "m2_research_state",
    "gap_analysis": "m2_gap_analysis",
    "reference_confirm": "m2_reference_confirm",
    "output_gen": "m2_output_gen",
    "DONE": "END",
}


def _route_to_next(state: M2SubGraphState) -> str:
    """Read current_phase, return the matching node name (or END).

    Decision: single router for all edges (START → node, node → node/END) so
    self-loops, jump-backs, and linear advances all share the same logic path.
    """
    phase = state.get("current_phase", "familiarize")
    if phase == "DONE":
        return "END"
    return _PHASE_TO_NODE_NAME.get(phase, "m2_familiarize")


def build_m2_subgraph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    """Compile the M2 sub-graph with conditional edges supporting self-loops + jumps."""
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    builder = StateGraph(M2SubGraphState)
    builder.add_node("m2_familiarize", phase1_familiarize.run)
    builder.add_node("m2_research_state", phase2_research_state.run)
    builder.add_node("m2_gap_analysis", phase3_gap_analysis.run)
    builder.add_node("m2_reference_confirm", phase4_reference_confirm.run)
    builder.add_node("m2_output_gen", phase5_output_gen.run)

    # START routes to whichever phase the state says we're at (allows resume).
    builder.add_conditional_edges(START, _route_to_next, {
        "m2_familiarize": "m2_familiarize",
        "m2_research_state": "m2_research_state",
        "m2_gap_analysis": "m2_gap_analysis",
        "m2_reference_confirm": "m2_reference_confirm",
        "m2_output_gen": "m2_output_gen",
        "END": END,
    })

    # Every phase node uses the same router: self-loop if phase unchanged, advance/jump otherwise.
    for node in ["m2_familiarize", "m2_research_state", "m2_gap_analysis",
                 "m2_reference_confirm", "m2_output_gen"]:
        builder.add_conditional_edges(node, _route_to_next, {
            "m2_familiarize": "m2_familiarize",
            "m2_research_state": "m2_research_state",
            "m2_gap_analysis": "m2_gap_analysis",
            "m2_reference_confirm": "m2_reference_confirm",
            "m2_output_gen": "m2_output_gen",
            "END": END,
        })

    interrupt_before = [] if not interactive else [
        "m2_familiarize", "m2_research_state", "m2_gap_analysis",
        "m2_reference_confirm", "m2_output_gen",
    ]
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


@lru_cache(maxsize=2)
def get_m2_graph(interactive: bool = True):
    """Cached singleton — uses the same PostgresSaver as the outer graph."""
    from orchestrator.graph import _get_pool
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_m2_subgraph(interactive=interactive, checkpointer=saver)
