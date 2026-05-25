"""Auto-mode roundtrip test for M4 agent — validates schema-driven auto-fill."""
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_m4_auto_produces_outline_and_results(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"data_type_detected":"SPSS",'
        '"analysis_outline":{"sections":["Descriptive","Reliability"],"confirmed_by_user":true},'
        '"results":{"descriptive":{"n":300}},'
        '"interpretations":{"descriptive":"Sample of 300..."}}'
    )
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="analyze")], "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"design": "Regression", "tool": "SPSS",
                       "confirmed_at": "2026-05-26"}),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M4Agent().step(state)
    assert res.transition is True
    assert res.context_patch["data_type_detected"] == "SPSS"
