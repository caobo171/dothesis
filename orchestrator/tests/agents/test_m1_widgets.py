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
    """Free-text M1 fields (not in card_fields) get no widget hint."""
    agent = M1Agent()
    for f in ("research_title", "target_population", "scope", "objectives", "research_questions"):
        assert agent.render_hint_for_field(f) is None, f"Expected None for {f}"


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
