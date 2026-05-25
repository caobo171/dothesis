"""Auto-mode roundtrip test for M2 agent — validates schema-driven auto-fill."""
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from orchestrator.agents.m2_literature import M2Agent
from orchestrator.state import ContextStore


def test_m2_auto_fills_required_fields(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"research_state_summary":"...","research_gaps":[{"description":"SME gap",'
        '"relevance":"High","supporting_papers":[],"confirmed":true}],'
        '"theoretical_framework":"TL","hypotheses":["H1"],'
        '"literature_review_doc":"...","citation_list":[]}'
    )
    monkeypatch.setattr(M2Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="literature review for leadership")],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL→EE", "research_type": "quantitative",
                      "confirmed_at": "2026-05-26T00:00:00"}
        ),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    res = M2Agent().step(state)
    assert res.transition is True
    assert res.context_patch["research_gaps"][0]["description"] == "SME gap"
