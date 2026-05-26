"""Tests for Phase 3 — Gap_Analysis."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


_GAP_JSON = (
    '[{"id":"1","description":"No SME context",'
    '"relevance":"High","supporting_papers":[]},'
    '{"id":"2","description":"Mediator untested",'
    '"relevance":"Medium","supporting_papers":[]}]'
)


def _state(mode="interactive", user_msg="start"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s["research_state_draft"] = "synthesis from phase 2"
    s["research_state_citations"] = [{"title": "P1"}]
    return s


def test_phase3_first_call_proposes_gaps(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    patch = phase3_gap_analysis.run(_state())
    gaps = patch["candidate_gaps"]
    assert len(gaps) == 2
    assert gaps[0]["description"] == "No SME context"


def test_phase3_select_advances_to_reference_confirm(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="use gap 1 and gap 2")
    s["candidate_gaps"] = [
        {"id": "1", "description": "g1"},
        {"id": "2", "description": "g2"},
    ]
    patch = phase3_gap_analysis.run(s)
    assert patch.get("selected_gap_ids") == ["1", "2"]
    assert patch.get("current_phase") == "reference_confirm"


def test_phase3_refine_regenerates(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo, focus on methodological gaps")
    s["candidate_gaps"] = [{"id": "1", "description": "old gap"}]
    patch = phase3_gap_analysis.run(s)
    assert patch["candidate_gaps"][0]["description"] == "No SME context"
    assert patch["gap_refinements"] == ["redo, focus on methodological gaps"]


def test_phase3_regen_cap_blocks_6th(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo")
    s["candidate_gaps"] = [{"id": "1"}]
    s["regeneration_count"] = {"gap_analysis": 5}
    patch = phase3_gap_analysis.run(s)
    fake_llm.invoke.assert_not_called()


def test_phase3_auto_selects_all(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    patch = phase3_gap_analysis.run(_state(mode="auto"))
    assert patch.get("selected_gap_ids") == ["1", "2"]
    assert patch.get("current_phase") == "reference_confirm"
