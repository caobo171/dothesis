"""Tests for Phase 1 — Familiarize."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


# First-call default is an EMPTY user message: in the real flow M2 is entered
# with no message of its own (the triggering "yes" belonged to M1's confirm), so
# phase 1 asks its opening question rather than classifying a stale reply. A
# non-empty user_msg simulates a RESUME turn where the user answered phase 1.
def _state(mode="interactive", paper_uris=None, user_msg=""):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=paper_uris or [], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    return s


def test_phase1_first_call_with_no_uploads_asks_question(monkeypatch):
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Do you have papers to upload?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(_state())
    assert patch.get("has_uploaded_papers") is None
    msgs = patch.get("messages", [])
    assert len(msgs) == 1
    assert "papers" in msgs[0].content.lower()


def test_phase1_with_uploads_lists_filenames(monkeypatch):
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "I see 2 papers — use them?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(_state(paper_uris=["s3://b/a.pdf", "s3://b/b.pdf"]))
    msgs = patch.get("messages", [])
    assert any("2" in m.content or "papers" in m.content.lower() for m in msgs)


def test_phase1_resume_after_confirm_advances(monkeypatch):
    from orchestrator.agents.m2.phases import phase1_familiarize
    from orchestrator.agents.m2 import intent as m2_intent
    s = _state(paper_uris=["s3://b/a.pdf"], user_msg="yes use them")
    s["has_uploaded_papers"] = None
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: MagicMock())

    # LLM-classified intent: confirm.
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(action="confirm")
    fake_intent = MagicMock()
    fake_intent.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent)

    patch = phase1_familiarize.run(s)
    assert patch.get("has_uploaded_papers") is True
    assert patch.get("current_phase") == "research_state"


def test_phase1_auto_mode_advances_immediately():
    from orchestrator.agents.m2.phases import phase1_familiarize
    patch = phase1_familiarize.run(_state(mode="auto", paper_uris=["s3://b/a.pdf"]))
    assert patch.get("has_uploaded_papers") is True
    assert patch.get("current_phase") == "research_state"


def test_phase1_auto_mode_no_papers_also_advances():
    from orchestrator.agents.m2.phases import phase1_familiarize
    patch = phase1_familiarize.run(_state(mode="auto", paper_uris=[]))
    assert patch.get("has_uploaded_papers") is False
    assert patch.get("current_phase") == "research_state"


def test_phase1_first_call_emits_card_grid_widget(monkeypatch):
    """W1: phase1 must emit interactive cards, not plain prose. The user
    explicitly asked that every M2 question come with widgets — typing the
    free-form reply into a chat box was the failure mode (M1 stored
    'Other / Specify' as the actual scope value).

    No uploads: only two real choices — let AI search, or pause to upload."""
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Do you have papers to upload?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(_state())
    hint = patch.get("tool_calls_json")
    assert hint is not None, "phase1 should emit a widget hint, not just prose"
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "familiarize_choice"
    values = {o["value"] for o in hint["options"]}
    assert "ai_search" in values
    # The hint must also be attached to the AIMessage so the frontend
    # WidgetRenderer (which reads additional_kwargs.tool_calls_json) can pick
    # it up — graph.py:77 propagates that field end-to-end.
    msg = patch["messages"][0]
    assert msg.additional_kwargs.get("tool_calls_json") == hint


def test_phase1_with_uploads_includes_use_papers_option(monkeypatch):
    """When the project already has uploaded papers, the card grid must
    include a 'use my papers' option — otherwise the user can't actually
    choose to rely on what they uploaded."""
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "I see 2 papers — use them?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(
        _state(paper_uris=["s3://b/a.pdf", "s3://b/b.pdf"])
    )
    hint = patch.get("tool_calls_json")
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert "use_papers" in values
    assert "ai_search" in values
