"""Tests for Phase 5 — Output_Gen."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="auto"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content="write")]
    s["research_state_draft"] = "synthesis"
    s["candidate_gaps"] = [{"id": "1", "description": "g1",
                            "supporting_papers": []}]
    s["selected_gap_ids"] = ["1"]
    s["verified_refs"] = [{"author": "X", "year": 2024, "page": 12, "verified": True}]
    s["research_state_citations"] = [{"author": "Y", "year": 2023, "title": "T1"}]
    return s


def test_phase5_writes_ch2_and_advances_to_done(monkeypatch):
    from orchestrator.agents.m2.phases import phase5_output_gen
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "2.1 Theoretical Foundation\n...\n"
        "2.2 Empirical Studies\n...\n"
        "2.3 Research Gaps\n...\n"
        "2.4 Theoretical Framework\nTransformational Leadership Theory"
    )
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: fake_llm)

    patch = phase5_output_gen.run(_state())
    assert patch.get("current_phase") == "DONE"
    assert "Theoretical Foundation" in patch.get("ch2_draft", "")
    assert patch.get("citation_list") == [{"author": "Y", "year": 2023, "title": "T1"}]


def test_phase5_marks_unverified_pages(monkeypatch):
    from orchestrator.agents.m2.phases import phase5_output_gen
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Chapter 2 mentions [page?] for unverified."
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: fake_llm)

    s = _state()
    s["verified_refs"] = [{"author": "X", "year": 2024, "page": 12, "verified": False}]
    patch = phase5_output_gen.run(s)
    assert "[page?]" in patch.get("ch2_draft", "")
