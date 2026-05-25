"""Auto-mode roundtrip test for M1 agent — validates schema-driven auto-fill."""
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from orchestrator.agents.m1_topic import M1Agent
from orchestrator.state import ContextStore


def test_m1_auto_produces_valid_output(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"research_title": "Impact of TL on EE", "field": "Marketing", '
        '"research_type": "quantitative", "target_population": "SME employees", '
        '"scope": "Vietnam 2026", "objectives": ["Test H1"], '
        '"research_questions": ["Does TL affect EE?"]}'
    )
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    res = M1Agent().step(state)
    assert res.transition is True
    assert res.context_patch["research_title"]
    assert "confirmed_at" in res.context_patch
