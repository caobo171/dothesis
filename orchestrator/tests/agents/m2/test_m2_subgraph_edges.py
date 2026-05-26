"""Tests that the sub-graph respects phase transitions and self-loops."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


def _stub_all_phases_to_advance(monkeypatch):
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )
    monkeypatch.setattr(phase1_familiarize, "run", lambda s: {"current_phase": "research_state"})
    monkeypatch.setattr(phase2_research_state, "run", lambda s: {"current_phase": "gap_analysis"})
    monkeypatch.setattr(phase3_gap_analysis, "run", lambda s: {"current_phase": "reference_confirm"})
    monkeypatch.setattr(phase4_reference_confirm, "run", lambda s: {"current_phase": "output_gen"})
    monkeypatch.setattr(phase5_output_gen, "run", lambda s: {"current_phase": "DONE"})


def test_subgraph_walks_linearly_when_all_advance(monkeypatch):
    _stub_all_phases_to_advance(monkeypatch)
    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="auto")
    final = g.invoke(s, config={"configurable": {"thread_id": "linear"}})
    assert final["current_phase"] == "DONE"


def test_subgraph_self_loop_when_phase_returns_same_phase(monkeypatch):
    """Phase 2 returns current_phase=research_state once, then advances."""
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    iteration = {"n": 0}
    def phase2_alternating(s):
        iteration["n"] += 1
        if iteration["n"] == 1:
            return {"current_phase": "research_state",
                    "regeneration_count": {"research_state": 1}}
        return {"current_phase": "gap_analysis"}

    monkeypatch.setattr(phase1_familiarize, "run", lambda s: {"current_phase": "research_state"})
    monkeypatch.setattr(phase2_research_state, "run", phase2_alternating)
    monkeypatch.setattr(phase3_gap_analysis, "run", lambda s: {"current_phase": "reference_confirm"})
    monkeypatch.setattr(phase4_reference_confirm, "run", lambda s: {"current_phase": "output_gen"})
    monkeypatch.setattr(phase5_output_gen, "run", lambda s: {"current_phase": "DONE"})

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="auto")
    final = g.invoke(s, config={"configurable": {"thread_id": "selfloop"}})
    assert final["current_phase"] == "DONE"
    assert iteration["n"] == 2
