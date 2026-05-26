"""Tests for M3Agent.render_hint_for_field overrides."""
from orchestrator.agents.m3_design import M3Agent


def test_tool_returns_card_grid_quant_options():
    """When the resolved paradigm is quant, `tool` widget shows quant tools."""
    agent = M3Agent()
    M3Agent._render_paradigm = "quantitative"
    hint = agent.render_hint_for_field("tool")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "tool"
    values = {o["value"] for o in hint["options"]}
    assert "SmartPLS" in values
    assert "NVivo" not in values  # qual-only tool should not appear in quant grid


def test_tool_returns_card_grid_qual_options():
    agent = M3Agent()
    M3Agent._render_paradigm = "qualitative"
    hint = agent.render_hint_for_field("tool")
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert "NVivo" in values
    assert "SmartPLS" not in values


def test_design_returns_card_grid_qual_options_only_for_qual():
    """For qual paradigm, `design` shows the four qual designs. For quant, the
    agent prefers free-text (so `design` returns None) since recommend_methodology
    handles it conversationally."""
    agent = M3Agent()
    M3Agent._render_paradigm = "qualitative"
    hint = agent.render_hint_for_field("design")
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert "Thematic Analysis" in values
    assert "Grounded Theory" in values

    M3Agent._render_paradigm = "quantitative"
    assert agent.render_hint_for_field("design") is None


def test_mixed_design_type_returns_card_grid_with_two_options():
    agent = M3Agent()
    M3Agent._render_paradigm = "mixed"
    hint = agent.render_hint_for_field("mixed_design_type")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    values = {o["value"] for o in hint["options"]}
    assert values == {"sequential_explanatory", "sequential_exploratory"}


def test_free_text_fields_return_none():
    agent = M3Agent()
    M3Agent._render_paradigm = "quantitative"
    for f in ("sampling_strategy", "target_sample_size"):
        assert agent.render_hint_for_field(f) is None, f"Expected None for {f}"
