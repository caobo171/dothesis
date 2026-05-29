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
    def render_hint_for_field(self, field_name, partial=None):
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


def test_summary_phase_emits_confirm_button_widget(monkeypatch):
    """All fields filled → summary path emits a card_grid with Confirm/Edit
    buttons so the user can one-click move on instead of typing.

    Replaces the older expectation that summary had no widget. The button
    flow ships in tandem with the LLM-based _is_affirmative (button sends
    literal 'yes' which the fast path accepts without an LLM call).
    """
    fake = MagicMock()
    fake.invoke.return_value.content = "Summary..."
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    result = _HintingAgent().step(_state(
        [HumanMessage("hello")],  # not a literal "yes" — stays in summary phase
        partial={"color": "red", "shape": "circle"},
    ))
    assert result.tool_calls_json is not None
    assert result.tool_calls_json["widget_type"] == "card_grid"
    assert result.tool_calls_json["field_name"] == "_confirm"
    values = {o["value"] for o in result.tool_calls_json["options"]}
    assert values == {"yes", "no"}


def test_no_hint_in_auto_mode(monkeypatch):
    """Auto-mode skips _ask_next_question entirely; tool_calls_json stays None."""
    fake = MagicMock()
    fake.invoke.return_value.content = '{"color": "red", "shape": "circle"}'
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    state = _state([HumanMessage("topic")])
    state["mode"] = "auto"
    result = _HintingAgent().step(state)
    assert result.tool_calls_json is None


def _llm_with_responses(monkeypatch, responses: list[str]) -> MagicMock:
    """Patch _HintingAgent._get_llm to return responses in order across .invoke calls."""
    fake = MagicMock()
    fake.invoke.side_effect = [MagicMock(content=r) for r in responses]
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    return fake


def test_clarification_intent_triggers_explain_and_keeps_awaiting_field(monkeypatch):
    """LLM classifier returns intent='clarification' → explanation fires,
    _awaiting_field stays set, conversation does NOT advance."""
    explanation = "Color here means the dominant hue of your subject. What color fits best?"
    # Two LLM calls expected: (1) classifier returns JSON, (2) explain_and_reask returns prose.
    _llm_with_responses(monkeypatch, [
        '{"intent": "clarification", "value": null}',
        explanation,
    ])

    state = _state(
        [HumanMessage("hi"), HumanMessage("I dont understand")],
        partial={"_awaiting_field": "color"},
    )
    result = _HintingAgent().step(state)

    assert result.assistant_message == explanation
    assert result.context_patch.get("color") is None
    assert result.context_patch.get("_awaiting_field") == "color"
    assert result.transition is False
    assert result.needs_user_reply is True


def test_bare_question_mark_classified_as_clarification(monkeypatch):
    """LLM classifier sees the bare '?' as clarification intent."""
    _llm_with_responses(monkeypatch, [
        '{"intent": "clarification", "value": null}',
        "Let me explain what shape means...",
    ])

    state = _state(
        [HumanMessage("?")],
        partial={"color": "red", "_awaiting_field": "shape"},
    )
    result = _HintingAgent().step(state)
    assert result.context_patch.get("_awaiting_field") == "shape"


def test_long_multiline_answer_classified_as_answer_not_clarification(monkeypatch):
    """REGRESSION: labeled-list answers containing keywords like 'what is' /
    'for example' MUST be classified as 'answer' by the LLM, not as a
    clarification. Pre-refactor, the keyword substring match would
    infinite-loop on this kind of reply.

    The LLM is shown the partial context + reply and is explicitly told that
    keyword-containing multi-item replies are still answers.
    """
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"intent": "answer", "value": ["round", "square", "triangle"]}'
    )
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)

    answer = (
        "My shapes are:\n"
        "- What is the most common shape?\n"
        "- For example a triangle\n"
        "- A circle is another option"
    )
    state = _state(
        [HumanMessage(answer)],
        partial={"color": "red", "_awaiting_field": "shape"},
    )
    result = _HintingAgent().step(state)

    assert result.context_patch.get("shape") == ["round", "square", "triangle"]
    assert result.context_patch.get("_awaiting_field") != "shape"


def test_classifier_failure_falls_back_to_dedicated_extractor(monkeypatch):
    """If the intent classifier returns malformed JSON, the step() loop falls
    back to _extract_answer so the conversation can still progress."""
    # First call (classifier): garbage. Second call (extractor): proper extraction.
    _llm_with_responses(monkeypatch, [
        "not-json-at-all",
        '{"field": "shape", "value": "circle"}',
    ])

    state = _state(
        [HumanMessage("a circle")],
        partial={"color": "red", "_awaiting_field": "shape"},
    )
    result = _HintingAgent().step(state)
    assert result.context_patch.get("shape") == "circle"
