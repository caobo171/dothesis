"""Auto-mode roundtrip test for M5 agent — validates schema-driven auto-fill."""
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_m5_auto_composes_and_exports(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"sections":[{"name":"intro","text":"..."},{"name":"lit_review","text":"..."}],'
        '"export_artifacts":[{"kind":"docx","uri":"/tmp/x.docx","size_bytes":1024},'
        '{"kind":"pdf","uri":"/tmp/x.pdf","size_bytes":2048}]}'
    )
    monkeypatch.setattr(M5Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="write")], "current_module": "M5",
        "context_store": ContextStore(
            m1_topic={"research_title": "X", "confirmed_at": "2026-05-26"},
            m2_literature={"literature_review_doc": "...", "confirmed_at": "2026-05-26"},
        ),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M5Agent().step(state)
    assert res.transition is True
    assert any(a["kind"] == "docx" for a in res.context_patch["export_artifacts"])
