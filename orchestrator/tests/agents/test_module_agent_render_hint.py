"""Tests for ModuleAgent.render_hint_for_field hook + ModuleStepResult.tool_calls_json."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleAgent
from orchestrator.state import ContextStore


class _ToyOutput(BaseModel):
    color: str = Field(..., min_length=1)
    shape: str = Field(..., min_length=1)


class _PlainAgent(ModuleAgent):
    schema = _ToyOutput
    module_key = "M1"
    tools = []
    system_prompt = "toy"


class _HintingAgent(_PlainAgent):
    def render_hint_for_field(self, field_name):
        if field_name == "color":
            return {
                "widget_type": "card_grid",
                "field_name": "color",
                "title": "Pick a color",
                "options": [{"value": "red", "label": "Red"}],
                "columns": 3,
            }
        return None


def _state(messages, partial=None):
    cs = ContextStore()
    if partial:
        cs.m1_topic = partial
    return {
        "project_id": None, "thread_id": None, "messages": messages,
        "current_module": "M1", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    }


def test_default_hook_returns_none(monkeypatch):
    """Base class default → ModuleStepResult.tool_calls_json is None."""
    fake = MagicMock()
    fake.invoke.return_value.content = "What color?"
    monkeypatch.setattr(_PlainAgent, "_get_llm", lambda self: fake)
    result = _PlainAgent().step(_state([HumanMessage("start")]))
    assert result.tool_calls_json is None


def test_subclass_override_attaches_hint(monkeypatch):
    """Subclass that overrides → hint flows into ModuleStepResult."""
    fake = MagicMock()
    fake.invoke.return_value.content = "What color?"
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    result = _HintingAgent().step(_state([HumanMessage("start")]))
    assert result.tool_calls_json is not None
    assert result.tool_calls_json["widget_type"] == "card_grid"
    assert result.tool_calls_json["field_name"] == "color"


def test_no_hint_when_summary_phase(monkeypatch):
    """When all fields filled, summary path emits no hint."""
    fake = MagicMock()
    fake.invoke.return_value.content = "Summary..."
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    result = _HintingAgent().step(_state(
        [HumanMessage("yes")],
        partial={"color": "red", "shape": "circle"},
    ))
    assert result.tool_calls_json is None


def test_no_hint_in_auto_mode(monkeypatch):
    """Auto-mode skips _ask_next_question entirely; tool_calls_json stays None."""
    fake = MagicMock()
    fake.invoke.return_value.content = '{"color": "red", "shape": "circle"}'
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    state = _state([HumanMessage("topic")])
    state["mode"] = "auto"
    result = _HintingAgent().step(state)
    assert result.tool_calls_json is None
