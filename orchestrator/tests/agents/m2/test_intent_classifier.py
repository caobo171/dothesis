"""Tests for M2's per-phase intent classifier."""
from unittest.mock import MagicMock

import pytest
from orchestrator.agents.m2.intent import (
    PhaseIntent, classify_phase_intent,
)


def test_classify_confirm_via_rule(monkeypatch):
    intent = classify_phase_intent(
        last_user_message="ok looks good",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "confirm"


def test_classify_refine_via_rule(monkeypatch):
    intent = classify_phase_intent(
        last_user_message="redo focusing on Self-Determination Theory",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"
    assert "Self-Determination" in intent.refinement_text


def test_classify_navigate_back(monkeypatch):
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
    fake = MagicMock()
    fake.with_structured_output.return_value.invoke.return_value = PhaseIntent(
        action="refine", refinement_text="add SDT", target_phase=None,
    )
    monkeypatch.setattr("orchestrator.agents.m2.intent._intent_llm", lambda: fake)
    intent = classify_phase_intent(
        last_user_message="hmm something about motivation",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"


def test_select_gaps_in_phase_3():
    intent = classify_phase_intent(
        last_user_message="use gap 1 and gap 3",
        current_phase="gap_analysis",
        mode="interactive",
    )
    assert intent.action == "select"
    assert intent.selected_ids == ["1", "3"]
