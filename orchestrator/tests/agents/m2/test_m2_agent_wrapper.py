"""Tests for M2Agent wrapper — outer-state → sub-graph → context_store output."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

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


def test_m2_agent_partial_state_does_not_transition(monkeypatch):
    """Sub-graph paused at a phase interrupt — wrapper returns transition=False."""
    from orchestrator.agents.m2 import M2Agent
    fake_subgraph = MagicMock()
    fake_subgraph.invoke.return_value = {
        "current_phase": "research_state",
        "research_state_draft": "partial",
        "messages": [HumanMessage(content="What's your topic?")],
    }
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent.get_m2_graph", lambda interactive: fake_subgraph
    )
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session",
        lambda: _FakeDbSession(),
    )

    agent = M2Agent()
    result = agent.step(_outer_state(mode="interactive"))
    assert result.transition is False
    assert result.needs_user_reply is True
