"""Sub-graph auto-mode end-to-end — all 5 phases run, produces ch2_draft + citations."""
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def _llm_for(content: str):
    m = MagicMock()
    m.invoke.return_value.content = content
    return m


def _stub_llms_and_tools(monkeypatch):
    from orchestrator.agents.m2.phases import (
        phase2_research_state, phase3_gap_analysis, phase4_reference_confirm,
        phase5_output_gen,
    )
    monkeypatch.setattr(phase2_research_state, "_scout",
                        lambda *a, **kw: [{"title": "P1", "authors": "Wang",
                                            "year": 2011, "source": "J", "url": None}])
    monkeypatch.setattr(phase2_research_state, "_get_llm",
                        lambda: _llm_for("Synthesis with (Wang, 2011)."))
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm",
                        lambda: _llm_for(
                            '[{"id":"1","description":"No SME context","relevance":"High",'
                            '"supporting_papers":[{"author":"Wang","year":2011,"page":118}]}]'
                        ))
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())
    monkeypatch.setattr(phase5_output_gen, "_get_llm",
                        lambda: _llm_for("Chapter 2 draft text."))


def test_subgraph_auto_runs_to_done_with_artifacts(monkeypatch):
    _stub_llms_and_tools(monkeypatch)

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(
        project_id="p", thread_id="t",
        research_title="TL on EE", research_type="quantitative",
        language="en", paper_uris=[], mode="auto",
    )
    final = g.invoke(s, config={"configurable": {"thread_id": "auto-e2e"}})

    assert final["current_phase"] == "DONE"
    assert final["research_state_draft"] and "Wang" in final["research_state_draft"]
    assert final["selected_gap_ids"] == ["1"]
    assert final["ch2_draft"]
