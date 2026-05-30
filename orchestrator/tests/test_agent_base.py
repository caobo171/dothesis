"""Tests for ModuleAgent's clarification loop (shared by all 5 module agents)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.state import ContextStore, OrchestratorState


class _ToyOutput(BaseModel):
    title: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    confirmed_at: datetime | None = None


class _ToyAgent(ModuleAgent):
    schema = _ToyOutput
    module_key = "M1"
    tools = []
    system_prompt = "You are a toy agent."


def _state(messages, partial=None, mode="interactive"):
    cs = ContextStore()
    if partial:
        cs.m1_topic = partial
    return {
        "project_id": None,
        "thread_id": None,
        "messages": messages,
        "current_module": "M1",
        "context_store": cs,
        "mode": mode,
        "user_intent": None,
        "pending_confirmations": [],
    }


def test_recent_dialogue_windows_last_turns_and_labels_roles():
    agent = _ToyAgent()
    msgs = [
        HumanMessage(content="m1"), AIMessage(content="a1"),
        HumanMessage(content="m2"), AIMessage(content="a2"),
        HumanMessage(content="m3"),
    ]
    transcript = agent._recent_dialogue(msgs, max_msgs=3)
    # Only the last 3 messages, oldest-first, labelled by role.
    assert "m1" not in transcript
    assert transcript == "User: m2\nAssistant: a2\nUser: m3"


@pytest.mark.parametrize("intent_value", ["meta", "frustration"])
def test_classify_recognizes_meta_and_frustration(monkeypatch, intent_value):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content=f'{{"intent": "{intent_value}", "value": null}}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="how long will this take?")])
    out = agent._classify_user_intent(state, "title", {"answer": "Y"})
    assert out["intent"] == intent_value


def test_answer_and_anchor_returns_concierge_message(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content="Good question! I'll handle citations later. "
                "Back to it — what's your title?"
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="does APA need a DOI?")])
    msg = agent._answer_and_anchor(state, "off_topic", "title", {"answer": "Y"})
    assert "title" in msg.lower()
    # The pending field must reach the LLM prompt.
    prompt = fake_llm.invoke.call_args[0][0]
    assert "title" in prompt


def test_off_topic_answers_then_reasks_same_field(monkeypatch):
    """A digression while awaiting a field → concierge reply that re-asks the
    SAME field (not advance, not silently re-ask, not store the digression)."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"intent": "off_topic", "value": null}'),          # classify
        AIMessage(content="Ha, weather's nice! Anyway — what's your title?"),  # concierge
    ]
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [AIMessage(content="What is the title?"),
         HumanMessage(content="btw what's the weather?")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    assert result.transition is False
    assert result.needs_user_reply is True
    assert "title" in result.assistant_message.lower()
    # Field stays pending so the next turn resumes correctly...
    assert result.context_patch.get("_awaiting_field") == "title"
    # ...and the digression was NOT stored as the field value.
    assert result.context_patch.get("title") is None
    # The reply must come from the concierge (answer-then-anchor), whose prompt
    # uniquely carries the user's digression (recent dialogue) AND the bridge
    # guidance — the old silent-re-ask path (_ask_next_question) carries neither.
    concierge_prompt = fake_llm.invoke.call_args_list[1][0][0]
    assert "weather" in concierge_prompt
    assert "bring them back" in concierge_prompt


def test_classifier_prompt_includes_recent_window(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content='{"intent": "answer", "value": "X"}')
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([
        AIMessage(content="Pick one: survey or interview?"),
        HumanMessage(content="the first one"),
    ])
    agent._classify_user_intent(state, "title", {})
    prompt = fake_llm.invoke.call_args[0][0]
    # The classifier must see the prior assistant turn to resolve "the first one".
    assert "survey or interview" in prompt


def test_interactive_asks_for_first_missing_field(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="What is the title?")
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="start")])
    result = agent.step(state)
    assert isinstance(result, ModuleStepResult)
    assert result.transition is False
    assert "title" in result.assistant_message.lower()


def test_interactive_fills_field_from_user_answer(monkeypatch):
    """When the agent has just asked for 'title' and user replies, it stores 'title'.

    Post-refactor flow per turn:
      1. _classify_user_intent  → JSON with intent + extracted value
      2. _ask_next_question     → prose prompt for the next field
    """
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"intent": "answer", "value": "My Title"}'),  # classify+extract
        AIMessage(content="Got it. What is the answer?"),                # next question
    ]
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [HumanMessage(content="start"),
         AIMessage(content="What is the title?"),
         HumanMessage(content="My Title")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    new_partial = result.context_patch
    assert new_partial.get("title") == "My Title"


def test_auto_mode_autofills_silently(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"title": "Auto Title", "answer": "Auto Answer"}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="seed topic")], mode="auto")
    result = agent.step(state)
    assert result.transition is True
    patch = result.context_patch
    assert patch["title"] == "Auto Title"
    assert patch["answer"] == "Auto Answer"
    assert "confirmed_at" in patch


def test_interactive_transition_after_confirm(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [AIMessage(content="Summary: title=X, answer=Y. Confirm?"),
         HumanMessage(content="yes")],
        partial={"title": "X", "answer": "Y", "_awaiting_confirm": True},
    )
    result = agent.step(state)
    assert result.transition is True
    assert "confirmed_at" in result.context_patch
