"""Auto-mode roundtrip test for M5 agent — validates schema-driven auto-fill
against the SP6 chapter-based schema."""
import json
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_m5_auto_produces_chapters_and_artifacts(monkeypatch):
    """In auto mode, _auto_fill asks the LLM for the full M5Output payload.
    SP6 expects `chapters` (dict keyed by chapter name) + at least one docx
    artifact when confirmed."""
    # Decision: auto-mode short-circuits to super().step() → _auto_fill, which
    # asks the LLM for the full payload in one shot. We stub _get_llm to return
    # a payload conforming to the SP6 chapter-based schema so the validator passes.
    chapters = {n: {"name": n, "prose": f"# {n}\nContent"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    payload = {
        "chapters": chapters,
        "bibliography": "Bass, A. (1990).",
        "export_artifacts": [{
            "kind": "docx",
            "s3_key": "projects/p/exports/x.docx",
            "download_url": "/api/v1/projects/p/exports/x.docx",
            "size_bytes": 1,
            "uri": "",
        }],
        "sections": [],
    }
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(payload)
    monkeypatch.setattr(M5Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="export")],
        "current_module": "M5",
        "project_id": "p",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    res = M5Agent().step(state)
    assert res.transition is True
    assert "chapters" in res.context_patch
    # All 6 chapter keys present (validator requires this on confirm)
    assert set(res.context_patch["chapters"].keys()) == {
        "intro", "lit_review", "methodology", "results", "discussion", "conclusion",
    }
