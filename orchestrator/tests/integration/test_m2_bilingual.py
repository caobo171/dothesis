"""Bilingual smoke — when language='vi', Phase 2 prompt threads 'vi' through."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.phases import phase2_research_state
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def test_vi_language_passed_into_phase2_prompt(monkeypatch):
    captured = {}
    def fake_llm():
        m = MagicMock()
        def invoke(prompt):
            captured["prompt"] = prompt
            msg = MagicMock()
            msg.content = "Tổng hợp tiếng Việt."
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])
    monkeypatch.setattr(phase2_research_state, "_get_llm", fake_llm)

    s = fresh_state(
        project_id="p", thread_id="t", research_title="TL→EE",
        research_type="quantitative", language="vi",
        paper_uris=[], mode="auto",
    )
    s["messages"] = [HumanMessage(content="start")]
    patch = phase2_research_state.run(s)
    assert "vi" in captured["prompt"]
    assert "Tiếng Việt" in patch["research_state_draft"] or "Việt" in patch["research_state_draft"]
