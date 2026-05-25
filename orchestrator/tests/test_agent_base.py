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
    """When the agent has just asked for 'title' and user replies, it stores 'title'."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"field": "title", "value": "My Title"}'),  # extraction
        AIMessage(content="Got it. What is the answer?"),               # next question
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
