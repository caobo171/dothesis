"""Tests for M2's per-phase intent classifier (LLM-first, no keyword rules)."""
from unittest.mock import MagicMock

import pytest
from orchestrator.agents.m2.intent import PhaseIntent, classify_phase_intent


def _mock_intent_llm(monkeypatch, intent: PhaseIntent) -> None:
    """Patch m2.intent._intent_llm so classify returns the provided intent."""
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = intent
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr("orchestrator.agents.m2.intent._intent_llm", lambda: fake_llm)


def test_classify_confirm_via_llm(monkeypatch):
    _mock_intent_llm(monkeypatch, PhaseIntent(action="confirm"))
    intent = classify_phase_intent(
        last_user_message="ok looks good",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "confirm"


def test_classify_refine_via_llm(monkeypatch):
    _mock_intent_llm(monkeypatch, PhaseIntent(action="refine"))
    intent = classify_phase_intent(
        last_user_message="redo focusing on Self-Determination Theory",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"
    # refinement_text is backfilled from the user message when the LLM didn't set it.
    assert "Self-Determination" in intent.refinement_text


def test_classify_navigate_back(monkeypatch):
    _mock_intent_llm(monkeypatch, PhaseIntent(
        action="navigate", target_phase="research_state",
    ))
    intent = classify_phase_intent(
        last_user_message="go back to research state",
        current_phase="gap_analysis",
        mode="interactive",
    )
    assert intent.action == "navigate"
    assert intent.target_phase == "research_state"


def test_classify_auto_mode_always_advances():
    intent = classify_phase_intent(
        last_user_message="anything",
        current_phase="research_state",
        mode="auto",
    )
    assert intent.action == "confirm"


def test_classify_ambiguous_falls_back_to_llm(monkeypatch):
    """The LLM is the primary classifier now — this test still pins the
    structured-output contract."""
    _mock_intent_llm(monkeypatch, PhaseIntent(action="refine"))
    intent = classify_phase_intent(
        last_user_message="hmm something about motivation",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"
    # refinement_text backfilled from the user message
    assert intent.refinement_text == "hmm something about motivation"


def test_select_gaps_via_regex_backfill(monkeypatch):
    """LLM picks the 'select' action; regex backfills the gap IDs from the
    user's natural phrasing — those IDs are bounded patterns, not keywords."""
    _mock_intent_llm(monkeypatch, PhaseIntent(action="select"))
    intent = classify_phase_intent(
        last_user_message="use gap 1 and gap 3",
        current_phase="gap_analysis",
        mode="interactive",
    )
    assert intent.action == "select"
    assert intent.selected_ids == ["1", "3"]


def test_correct_page_regex_backfill(monkeypatch):
    """LLM picks 'correct_page'; regex backfills the page number."""
    _mock_intent_llm(monkeypatch, PhaseIntent(action="correct_page"))
    intent = classify_phase_intent(
        last_user_message="correct, page 120 is right",
        current_phase="reference_confirm",
        mode="interactive",
    )
    assert intent.action == "correct_page"
    assert intent.corrected_page == 120


def test_empty_message_short_circuits_to_confirm():
    """Empty/whitespace user messages skip the LLM and default to confirm."""
    intent = classify_phase_intent(
        last_user_message="",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "confirm"
