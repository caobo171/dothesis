"""Tests for M2Agent wrapper — outer-state → sub-graph → context_store output."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.state import ContextStore


def _outer_state(mode="auto"):
    return {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "thread_id": "00000000-0000-0000-0000-000000000002",
        "messages": [HumanMessage(content="lit review please")],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL→EE", "research_type": "quantitative",
                      "language": "en", "confirmed_at": "2026-05-26"},
        ),
        "mode": mode,
    }


class _FakeDbSession:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def query(self, *a, **kw):
        m = MagicMock()
        m.filter_by.return_value.all.return_value = []
        return m


def test_m2_agent_runs_sub_graph_to_done(monkeypatch):
    """Stub the sub-graph to return a DONE final state; wrapper should flatten and transition."""
    from orchestrator.agents.m2 import M2Agent
    fake_subgraph = MagicMock()
    fake_subgraph.invoke.return_value = {
        "current_phase": "DONE",
        "research_state_draft": "synthesis",
        "candidate_gaps": [{"id": "1", "description": "g1", "supporting_papers": []}],
        "selected_gap_ids": ["1"],
        "verified_refs": [],
        "ch2_draft": "Chapter 2 text",
        "citation_list": [{"author": "X", "year": 2024}],
        "research_type": "quantitative",
    }
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent.get_m2_graph", lambda interactive: fake_subgraph
    )
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session",
        lambda: _FakeDbSession(),
    )

    agent = M2Agent()
    result = agent.step(_outer_state())
    assert result.transition is True
    patch_dict = result.context_patch
    assert patch_dict["literature_review_doc"] == "Chapter 2 text"
    assert patch_dict["research_state_summary"] == "synthesis"
    assert "confirmed_at" in patch_dict


def test_m2_interactive_first_turn_asks_question_and_persists_phase(monkeypatch):
    """Interactive M2 dispatches phase functions directly (no interrupt sub-graph).

    First turn: phase 1 asks its question and stays put (waiting on the user).
    The wrapper must surface that real question (not an empty string) and persist
    the phase pointer in context_patch['_phase_state'] so the next turn resumes.
    """
    from orchestrator.agents.m2 import M2Agent
    from orchestrator.agents.m2.phases import phase1_familiarize

    def fake_p1(state):
        # First call: ask about uploads, leave current_phase unchanged → pause.
        return {"messages": [AIMessage(content="Do you have papers to upload?")],
                "current_phase": "familiarize", "has_uploaded_papers": None}
    monkeypatch.setattr(phase1_familiarize, "run", fake_p1)
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session", lambda: _FakeDbSession())

    result = M2Agent().step(_outer_state(mode="interactive"))
    assert result.transition is False
    assert result.needs_user_reply is True
    assert "papers" in result.assistant_message.lower()
    assert result.context_patch["_phase_state"]["current_phase"] == "familiarize"


def test_m2_interactive_advances_and_runs_next_phase_same_turn(monkeypatch):
    """When the resuming phase advances without a message, the wrapper keeps
    running phases in the same turn until one pauses with a question — so the
    user never sees an empty turn, and the new phase pointer is persisted."""
    from orchestrator.agents.m2 import M2Agent
    from orchestrator.agents.m2.phases import phase1_familiarize, phase2_research_state

    def fake_p1(state):
        # Resume: user said "no papers" → advance, emit nothing.
        return {"current_phase": "research_state", "has_uploaded_papers": False}

    def fake_p2(state):
        # First research_state call: synthesize + ask, stay put.
        return {"messages": [AIMessage(content="Here is the research state — confirm?")],
                "current_phase": "research_state", "research_state_draft": "draft"}
    monkeypatch.setattr(phase1_familiarize, "run", fake_p1)
    monkeypatch.setattr(phase2_research_state, "run", fake_p2)
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session", lambda: _FakeDbSession())

    st = _outer_state(mode="interactive")
    st["context_store"].m2_literature = {"_phase_state": {"current_phase": "familiarize"}}
    st["messages"] = [HumanMessage(content="no I don't have papers")]

    result = M2Agent().step(st)
    assert result.transition is False
    assert "confirm" in result.assistant_message.lower()
    assert result.context_patch["_phase_state"]["current_phase"] == "research_state"


def test_m2_interactive_reaching_done_transitions(monkeypatch):
    """When a phase advances to DONE, the wrapper transitions (stamps confirmed_at)."""
    from orchestrator.agents.m2 import M2Agent
    from orchestrator.agents.m2.phases import phase5_output_gen

    def fake_p5(state):
        return {"current_phase": "DONE", "ch2_draft": "Ch2 text",
                "citation_list": [{"author": "X", "year": 2024}]}
    monkeypatch.setattr(phase5_output_gen, "run", fake_p5)
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session", lambda: _FakeDbSession())

    st = _outer_state(mode="interactive")
    st["context_store"].m2_literature = {"_phase_state": {"current_phase": "output_gen"}}

    result = M2Agent().step(st)
    assert result.transition is True
    assert "confirmed_at" in result.context_patch
    assert result.context_patch["literature_review_doc"] == "Ch2 text"
