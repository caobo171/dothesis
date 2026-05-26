"""Interactive walk through M2 phases — regen, cap, navigate.

Uses update_state + invoke(None) pattern (LangGraph 1.x interrupt_before behaviour):
each g.invoke(...) runs until the next interrupt_before point. To resume with new
user input we use Command(update={...}) which atomically patches the checkpoint and
resumes execution.

Flow for interrupt_before graphs:
  1. g.invoke(initial_state) → routes to node, hits interrupt_before → pauses
  2. g.invoke(Command(update={"messages": [...]})) → applies update then runs the node
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def _setup_stubs(monkeypatch):
    from orchestrator.agents.m2.phases import (
        phase2_research_state, phase3_gap_analysis, phase4_reference_confirm,
        phase5_output_gen,
    )
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])

    synth_counter = {"n": 0}
    def synth_llm():
        m = MagicMock()
        def invoke(prompt):
            synth_counter["n"] += 1
            msg = MagicMock()
            msg.content = (f"Synthesis v{synth_counter['n']}")
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase2_research_state, "_get_llm", synth_llm)

    gap_counter = {"n": 0}
    def gap_llm():
        m = MagicMock()
        def invoke(prompt):
            gap_counter["n"] += 1
            msg = MagicMock()
            msg.content = '[{"id":"1","description":"gap v' + str(gap_counter["n"]) + '","relevance":"High","supporting_papers":[]}]'
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", gap_llm)

    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    final_llm = MagicMock()
    final_llm.invoke.return_value.content = "Chapter 2 final."
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: final_llm)


def test_phase2_refines_once_then_confirms(monkeypatch):
    """Graph starts at research_state, produces draft, accepts one refine, then confirms."""
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p2-refine"}}

    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "research_state"

    # Step 1: initial invoke → interrupted before m2_research_state (no draft yet)
    g.invoke(s, config=config)
    # Step 2: run node with no user message → scouts (empty), synthesises → "Synthesis v1"
    #         node self-loops back to research_state, interrupts again before next run
    g.invoke(Command(update={"messages": []}), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values.get("research_state_draft") == "Synthesis v1"

    # Step 3: send a refine message → runs node with last_user="redo focus on SDT"
    g.invoke(Command(update={
        "messages": [HumanMessage(content="redo focus on SDT")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["research_state_draft"] == "Synthesis v2"
    assert snapshot.values["regeneration_count"]["research_state"] == 1

    # Step 4: send confirm → node advances phase to gap_analysis
    g.invoke(Command(update={
        "messages": [HumanMessage(content="confirm")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["research_state_confirmed"] is True
    assert snapshot.values["current_phase"] == "gap_analysis"


def test_phase2_regen_cap_blocks_6th_iteration(monkeypatch):
    """When regeneration_count["research_state"] is already 5, further refine is blocked."""
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p2-cap"}}

    # Seed state with draft already set and regen count at cap
    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "research_state"
    s["research_state_draft"] = "old synthesis"
    s["regeneration_count"] = {"research_state": 5}
    # Step 1: initial invoke → interrupted before m2_research_state
    g.invoke(s, config=config)

    # Step 2: send a refine request (exceeds cap) → should block, draft unchanged
    g.invoke(Command(update={
        "messages": [HumanMessage(content="redo one more time")],
    }), config=config)
    snapshot = g.get_state(config)
    # Draft must be unchanged — cap blocked the regeneration
    assert snapshot.values["research_state_draft"] == "old synthesis"
    # The assistant should have sent a message containing "lock" or "5"
    last_msg = snapshot.values["messages"][-1]
    assert "lock" in last_msg.content.lower() or "5" in last_msg.content


def test_navigate_back_from_gap_analysis_to_research_state(monkeypatch):
    """From gap_analysis, a 'go back to research state' message rewinds the phase pointer."""
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p3-nav"}}

    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "gap_analysis"
    s["research_state_draft"] = "synthesis"
    s["candidate_gaps"] = [{"id": "1", "description": "g1"}]
    # Step 1: initial invoke → interrupted before m2_gap_analysis
    g.invoke(s, config=config)

    # Step 2: run gap_analysis node with no message → proposes gaps, self-loops, interrupts
    g.invoke(Command(update={"messages": []}), config=config)

    # Step 3: send navigate-back message → node returns {"current_phase": "research_state"}
    g.invoke(Command(update={
        "messages": [HumanMessage(content="go back to research state")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["current_phase"] == "research_state"
