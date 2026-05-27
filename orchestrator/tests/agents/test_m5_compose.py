"""Tests for M5Agent compose phase — per-chapter AIMessage emission."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_compose_phase_emits_one_message_per_chapter_plus_bibliography(monkeypatch):
    """Compose phase emits 6 chapter messages + 1 bibliography message + 1 summary."""
    from orchestrator.agents import m5_writing as m5_mod

    fake_compose = MagicMock()
    fake_compose.invoke.side_effect = lambda kw: {
        "name": kw["chapter_name"],
        "prose": f"## Chapter — {kw['chapter_name']}\nContent",
        "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "compose_chapter", fake_compose)

    fake_bib = MagicMock()
    fake_bib.invoke.return_value = "Bass, A. (1990). Leadership."
    monkeypatch.setattr(m5_mod, "compile_bibliography", fake_bib)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M5",
        "project_id": "proj-xyz",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL → EE", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "2026-05-26"},
            m4_analysis={"data_type_detected": "SmartPLS", "results": {}, "confirmed_at": "2026-05-26"},
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)

    # 6 chapter AIMessages + 1 bibliography = 7 in extra_messages
    assert len(result.extra_messages) == 7
    contents = [m.content for m in result.extra_messages]
    assert any("intro" in c.lower() for c in contents)
    assert any("methodology" in c.lower() for c in contents)
    assert any("bibliography" in c.lower() for c in contents)

    # State updated correctly
    assert result.context_patch.get("_compose_chapters_done") is True
    assert result.context_patch.get("_awaiting_confirm") is True
    assert "chapters" in result.context_patch
    # 6 chapters in the dict
    assert len(result.context_patch["chapters"]) == 6


def test_compose_phase_passes_paradigm_to_each_chapter(monkeypatch):
    """The paradigm flows from m3_design to compose_chapter for each call."""
    from orchestrator.agents import m5_writing as m5_mod

    captured_paradigms = []
    def fake_invoke(kw):
        captured_paradigms.append(kw.get("paradigm"))
        return {"name": kw["chapter_name"], "prose": "x", "citations_used": [],
                "uncited_warnings": []}
    fake_compose = MagicMock()
    fake_compose.invoke.side_effect = fake_invoke
    monkeypatch.setattr(m5_mod, "compose_chapter", fake_compose)

    fake_bib = MagicMock()
    fake_bib.invoke.return_value = ""
    monkeypatch.setattr(m5_mod, "compile_bibliography", fake_bib)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage(content="go")],
        "current_module": "M5",
        "project_id": "p",
        "context_store": ContextStore(
            m3_design={"paradigm": "qualitative", "confirmed_at": "x"},
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    agent.step(state)
    assert len(captured_paradigms) == 6
    assert all(p == "qualitative" for p in captured_paradigms)
