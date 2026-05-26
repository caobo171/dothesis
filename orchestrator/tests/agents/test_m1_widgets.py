"""Tests for M1Agent.render_hint_for_field overrides."""
from orchestrator.agents.m1_topic import M1Agent


def test_field_returns_card_grid_hint():
    hint = M1Agent().render_hint_for_field("field")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "field"
    assert len(hint["options"]) >= 7
    assert any(o["value"] == "Marketing" for o in hint["options"])
    assert any(o["value"] == "Other" for o in hint["options"])


def test_research_type_returns_card_grid_hint():
    hint = M1Agent().render_hint_for_field("research_type")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "research_type"
    values = {o["value"] for o in hint["options"]}
    assert values == {"quantitative", "qualitative", "mixed"}


def test_text_fields_return_none():
    """Free-text M1 fields get no widget."""
    agent = M1Agent()
    for f in ("research_title", "target_population", "scope", "objectives", "research_questions"):
        assert agent.render_hint_for_field(f) is None, f"Expected None for {f}"


def test_hint_options_carry_description():
    """Description field is populated; helps the UI show secondary text."""
    hint = M1Agent().render_hint_for_field("field")
    marketing = next(o for o in hint["options"] if o["value"] == "Marketing")
    assert marketing["description"] != ""
