"""Tests for M1Agent's dynamic card-grid widget hints.

The original SP3 implementation loaded fixed JSON option lists from disk.
That was retired in favor of LLM-generated cards seeded from the partial
state (see ModuleAgent._generate_card_options). These tests pin the new
contract: M1 declares which fields render as cards, the base class calls
the LLM with the partial context, and the returned hint is a well-formed
CardGridHint dict.
"""
import json
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m1_topic import M1Agent


def _stub_llm_returning(monkeypatch, cards: list[dict]) -> MagicMock:
    """Patch M1Agent._get_llm so the LLM returns the supplied cards as JSON."""
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(cards)
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)
    return fake


def test_research_type_card_grid_renders_even_when_llm_fails(monkeypatch):
    """Reported bug: the bot said 'Pick one of the cards below, or type your
    own' but no cards appeared. Root cause: _generate_card_options is itself
    an LLM call that timed out / returned invalid JSON, so the dynamic
    options came back empty. For literal-bounded fields like research_type
    (Literal[quantitative|qualitative|mixed]) the answer is a static
    fallback — it should ALWAYS render those three options + Other, dynamic
    LLM or not.
    """
    fake = MagicMock()
    fake.invoke.return_value.content = "not even close to JSON"   # simulate failure
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    hint = M1Agent().render_hint_for_field(
        "research_type", partial={"research_title": "Gen Z"})
    assert hint is not None, "static fallback must produce a hint, not None"
    values = {o["value"] for o in hint["options"]}
    # The 3 schema-literal values must appear; Other is the escape hatch.
    assert {"quantitative", "qualitative", "mixed", "Other"}.issubset(values)


def test_field_returns_card_grid_hint(monkeypatch):
    """`field` is opted into card rendering and the LLM cards round-trip cleanly."""
    cards = [
        {"value": "Education", "label": "Education", "description": "Pedagogy + learning"},
        {"value": "Sociology", "label": "Sociology", "description": "Social structures"},
        {"value": "Other",     "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M1Agent().render_hint_for_field("field", partial={"research_title": "Gen Z social media"})

    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "field"
    assert hint["title"].startswith("Which academic field")
    assert [o["value"] for o in hint["options"]] == ["Education", "Sociology", "Other"]


def test_research_type_returns_card_grid_hint(monkeypatch):
    """`research_type` is opted in and the LLM-supplied cards flow through."""
    cards = [
        {"value": "qualitative", "label": "Qualitative", "description": "Themes + interviews"},
        {"value": "quantitative", "label": "Quantitative", "description": "Statistical tests"},
        {"value": "mixed",       "label": "Mixed", "description": "Both approaches"},
        {"value": "Other",       "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M1Agent().render_hint_for_field("research_type", partial={"field": "Education"})

    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "research_type"
    assert hint["title"].startswith("Which research approach")
    values = {o["value"] for o in hint["options"]}
    assert {"qualitative", "quantitative", "mixed", "Other"}.issubset(values)


def test_text_fields_return_none():
    """Truly free-text M1 fields get no widget hint.

    research_title is the user's seed input — nothing upstream to ground
    card suggestions in, so it stays as a text input.
    """
    agent = M1Agent()
    assert agent.render_hint_for_field("research_title") is None


def _stub_llm_returning_list(monkeypatch, items):
    """Patch M1Agent._get_llm so _generate_list_items returns `items`."""
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(items)
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)
    return fake


def test_objectives_returns_list_editor_hint(monkeypatch):
    """objectives is in list_fields → LLM-seeded ListEditorHint, flat (no nesting)."""
    items = [
        "Measure the correlation between TikTok engagement and purchase intent.",
        "Examine moderating effects of brand familiarity.",
        "Identify content types that drive highest engagement.",
    ]
    _stub_llm_returning_list(monkeypatch, items)

    hint = M1Agent().render_hint_for_field("objectives", partial={
        "research_title": "Gen Z TikTok marketing effectiveness",
        "field": "Marketing",
        "research_type": "quantitative",
    })

    assert hint is not None
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "objectives"
    assert hint["allow_nested"] is False
    assert hint["title"].lower().startswith("research objectives")
    assert [item["text"] for item in hint["initial_items"]] == items


def test_research_questions_returns_list_editor_hint(monkeypatch):
    """research_questions opts in via list_fields too."""
    items = [
        "How does TikTok engagement type predict purchase intent?",
        "Does brand familiarity moderate the engagement-purchase relationship?",
    ]
    _stub_llm_returning_list(monkeypatch, items)

    hint = M1Agent().render_hint_for_field("research_questions", partial={
        "research_title": "Gen Z TikTok marketing",
    })
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "research_questions"
    assert len(hint["initial_items"]) == 2


def test_list_editor_falls_back_to_none_when_llm_fails(monkeypatch):
    """LLM/JSON failure → no widget hint → caller falls back to free-text input."""
    fake = MagicMock()
    fake.invoke.side_effect = RuntimeError("network down")
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    assert M1Agent().render_hint_for_field("objectives", partial={}) is None


def test_hint_options_carry_description(monkeypatch):
    """The dynamic generator preserves the description field for the UI."""
    cards = [
        {"value": "Marketing", "label": "Marketing", "description": "Consumer behavior + branding"},
        {"value": "Other",     "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M1Agent().render_hint_for_field("field", partial={})
    marketing = next(o for o in hint["options"] if o["value"] == "Marketing")
    assert marketing["description"] == "Consumer behavior + branding"


def test_card_generation_falls_back_to_none_when_llm_fails(monkeypatch):
    """LLM/JSON failure must not crash the clarification loop — return None so
    the caller can show a plain-text input as fallback."""
    fake = MagicMock()
    fake.invoke.side_effect = RuntimeError("network down")
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    assert M1Agent().render_hint_for_field("field", partial={}) is None


def test_card_generation_drops_invalid_entries(monkeypatch):
    """Schema-invalid entries are dropped; valid ones still render."""
    cards = [
        {"value": "Education", "label": "Education", "description": "Valid"},
        {"missing_required_value": True},          # invalid → dropped
        {"value": "Other", "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M1Agent().render_hint_for_field("field", partial={})
    values = [o["value"] for o in hint["options"]]
    assert values == ["Education", "Other"]


def test_synthesized_field_sentence_extracts_to_value(monkeypatch):
    """The synthesized sentence 'I'd like to study Marketing.' should
    extract to the value 'Marketing' via ModuleAgent._extract_answer."""
    fake = MagicMock()
    fake.invoke.return_value.content = '{"field": "field", "value": "Marketing"}'
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    state = {
        "messages": [HumanMessage(content="I'd like to study Marketing.")],
        "current_module": "M1",
        "mode": "interactive",
    }
    extracted = agent._extract_answer(state, "field")
    assert extracted == "Marketing"


def test_synthesized_research_type_extracts_to_value(monkeypatch):
    """'I'll use a qualitative approach.' → 'qualitative'."""
    fake = MagicMock()
    fake.invoke.return_value.content = '{"field": "research_type", "value": "qualitative"}'
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    state = {
        "messages": [HumanMessage(content="I'll use a qualitative approach.")],
        "current_module": "M1",
        "mode": "interactive",
    }
    extracted = agent._extract_answer(state, "research_type")
    assert extracted == "qualitative"
