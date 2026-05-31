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


def test_phase3_refuses_to_generate_gaps_without_citations(monkeypatch):
    """B2: when research_state_citations is empty, phase3 must NOT call the
    LLM to generate gaps — without source data the LLM fabricates placeholder
    strings ({'author':'Author','year':'Year'}) which we surface to users as
    'Citation: Author (Year) page page?'. Refuse cleanly instead."""
    from orchestrator.agents.m2.phases import phase3_gap_analysis as p3
    fake_llm = MagicMock()
    monkeypatch.setattr(p3, "_get_llm", lambda: fake_llm)

    s = _state()
    s["research_state_citations"] = []  # no citations available
    patch = p3.run(s)

    fake_llm.invoke.assert_not_called()  # never reached
    assert patch.get("candidate_gaps") == []
    # User-visible note that explains why
    msg = (patch.get("messages") or [MagicMock(content="")])[0].content.lower()
    assert "citation" in msg or "source" in msg


def test_phase3_filters_placeholder_supporting_papers(monkeypatch):
    """B2 defense-in-depth: even if the LLM is called with real citations and
    still returns placeholder supporting_papers (literal 'Author'/'X'/'Year'),
    we filter them out so they never reach the user."""
    from orchestrator.agents.m2.phases import phase3_gap_analysis as p3
    fake_llm = MagicMock()
    # The LLM produces a real description but FAKE supporting_papers.
    fake_llm.invoke.return_value.content = (
        '[{"id":"1","description":"Real gap",'
        '"relevance":"High",'
        '"supporting_papers":[{"author":"Author","year":"Year","page":"page?"},'
        '                     {"author":"X","year":2020,"page":12},'
        '                     {"author":"Wang","year":2011,"page":118}]}]'
    )
    monkeypatch.setattr(p3, "_get_llm", lambda: fake_llm)

    s = _state()
    s["research_state_citations"] = [{"title": "P1", "authors": "Wang", "year": 2011}]
    patch = p3.run(s)

    gaps = patch["candidate_gaps"]
    assert len(gaps) == 1
    papers = gaps[0]["supporting_papers"]
    # Placeholders filtered; the real one (Wang 2011) survives.
    authors = {p.get("author") for p in papers}
    assert "Author" not in authors  # literal placeholder
    assert "X" not in authors  # generic schema example
    assert "Wang" in authors


def test_phase3_card_grid_includes_other_option(monkeypatch):
    """W5: gap card grid must include an Other option that opens text input
    so the user can describe a gap not in the LLM's list. The synthesizer
    routes the typed text to the add_custom_gap intent."""
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    hint = phase3_gap_analysis.run(_state()).get("tool_calls_json")
    values = {o["value"] for o in hint["options"]}
    assert "Other" in values


def test_phase3_first_call_emits_multi_select_card_grid(monkeypatch):
    """W2: phase3 must emit a multi-select card_grid of gap options instead
    of a 'use gap 1 and gap 3' prose prompt. The user explicitly asked that
    every M2 question come with interactive components, and gap selection is
    the highest-leverage one — multiple gaps are typically picked together,
    so multi-select avoids a serial click-confirm loop.

    Each gap becomes one card; the field_name is 'selected_gap_ids'."""
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    patch = phase3_gap_analysis.run(_state())
    hint = patch.get("tool_calls_json")
    assert hint is not None, "phase3 should emit a widget hint"
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "selected_gap_ids"
    assert hint.get("multi_select") is True
    # One card per gap, value = gap id, label includes the description.
    # 'Other' added by W5 is allowed alongside — the gap-IDs subset is what
    # matters here.
    values = {o["value"] for o in hint["options"]}
    assert {"1", "2"}.issubset(values)
    # AIMessage must also carry the hint for the frontend to render it.
    msg = patch["messages"][0]
    assert msg.additional_kwargs.get("tool_calls_json") == hint


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
    from orchestrator.agents.m2 import intent as m2_intent
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: MagicMock())

    # classify_phase_intent now always calls the LLM (keyword catches removed).
    # Mock it to return action="select" — the regex backfill in classify will
    # populate selected_ids from "gap 1 and gap 2" automatically.
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(action="select")
    fake_intent_llm = MagicMock()
    fake_intent_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent_llm)

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
