"""Tests for M5Agent rewrite detection + dispatch."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_is_rewrite_request_detects_keywords():
    agent = M5Agent()
    assert agent._is_rewrite_request([HumanMessage("rewrite chapter 3")]) is True
    assert agent._is_rewrite_request([HumanMessage("make it less formal")]) is True
    assert agent._is_rewrite_request([HumanMessage("expand the methodology")]) is True
    assert agent._is_rewrite_request([HumanMessage("yes, confirm")]) is False
    assert agent._is_rewrite_request([HumanMessage("looks good")]) is False


def test_identify_chapter_maps_aliases():
    agent = M5Agent()
    assert agent._identify_chapter("rewrite chapter 3") == "methodology"
    assert agent._identify_chapter("ch3 looks weird") == "methodology"
    assert agent._identify_chapter("rephrase the methodology") == "methodology"
    assert agent._identify_chapter("rewrite the intro") == "intro"
    assert agent._identify_chapter("introduction needs work") == "intro"
    assert agent._identify_chapter("expand the lit review") == "lit_review"
    assert agent._identify_chapter("results section") == "results"
    assert agent._identify_chapter("discussion") == "discussion"
    assert agent._identify_chapter("conclusion") == "conclusion"


def test_identify_chapter_returns_none_on_ambiguous():
    agent = M5Agent()
    assert agent._identify_chapter("something something") is None
    assert agent._identify_chapter("") is None


def test_handle_rewrite_calls_rewrite_chapter_and_updates_partial(monkeypatch):
    # SP6.5: rewrite now writes a PendingEdit instead of overwriting prose.
    # The rewrite_chapter tool may return a dict (with a "prose" key) or a plain
    # string; both are normalised to str before being stored in new_text.
    from orchestrator.agents import m5_writing as m5_mod

    fake_rewrite = MagicMock()
    fake_rewrite.invoke.return_value = {
        "name": "methodology",
        "prose": "Less formal methodology rewrite",
        "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "rewrite_chapter", fake_rewrite)

    agent = M5Agent()
    M5Agent._render_context = {
        "research_title": "x", "paradigm": "quantitative",
        "language": "en", "research_gaps": [],
    }
    partial = {
        "chapters": {"methodology": {"name": "methodology", "prose": "Formal version", "pending_edits": []}},
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = {
        "messages": [HumanMessage("rewrite chapter 3 to be less formal")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent._handle_rewrite(state, partial)

    # SP6.5: prose must NOT be overwritten; a PendingEdit is appended instead
    ch = result.context_patch["chapters"]["methodology"]
    assert ch["prose"] == "Formal version"
    assert len(ch["pending_edits"]) == 1
    edit = ch["pending_edits"][0]
    # When invoke returns a dict, the "prose" value is extracted as new_text
    assert edit["new_text"] == "Less formal methodology rewrite"
    assert edit["source"] == "chat_rewrite"
    assert result.context_patch["_awaiting_confirm"] is True
    assert len(result.extra_messages) == 1
    assert "methodology" in result.extra_messages[0].content.lower()
    # SP6.5: bubble says "ready" and links to editor, not "rewritten"
    assert "editor" in result.extra_messages[0].content.lower()


def test_handle_rewrite_asks_for_clarification_on_ambiguous(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod
    monkeypatch.setattr(m5_mod, "rewrite_chapter", MagicMock())

    agent = M5Agent()
    M5Agent._render_context = {"paradigm": "quantitative", "research_gaps": [], "language": "en"}
    partial = {"chapters": {}, "_compose_chapters_done": True, "_awaiting_confirm": True}
    state = {
        "messages": [HumanMessage("rewrite this thing please")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent._handle_rewrite(state, partial)
    assert result.context_patch["_awaiting_confirm"] is True
    assert "which chapter" in result.assistant_message.lower()
    # No rewrite happened
    assert result.extra_messages == []


def test_step_routes_rewrite_request_to_handle_rewrite(monkeypatch):
    """SP6.5 end-to-end: step() detects rewrite + dispatches to _handle_rewrite,
    which now appends a PendingEdit instead of overwriting prose."""
    from orchestrator.agents import m5_writing as m5_mod

    fake_rewrite = MagicMock()
    fake_rewrite.invoke.return_value = {
        "name": "intro", "prose": "New intro", "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "rewrite_chapter", fake_rewrite)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage("rewrite the intro to be shorter")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(
            m1_topic={"research_title": "x", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "x"},
            m5_writing={
                "chapters": {"intro": {"name": "intro", "prose": "old intro", "pending_edits": []}},
                "_compose_chapters_done": True,
                "_awaiting_confirm": True,
            },
        ),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)
    # SP6.5: prose must remain unchanged; new text lives in pending_edits
    assert result.context_patch["chapters"]["intro"]["prose"] == "old intro"
    edits = result.context_patch["chapters"]["intro"]["pending_edits"]
    assert len(edits) == 1
    assert edits[0]["new_text"] == "New intro"
    assert fake_rewrite.invoke.called
