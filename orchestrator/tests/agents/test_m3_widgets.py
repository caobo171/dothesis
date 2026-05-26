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


def test_themes_returns_list_editor_hint(monkeypatch):
    """themes hint is a list_editor with initial_items from suggest_themes."""
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_themes = [
        {"id": "t1", "theme": "Lãnh đạo", "sub_themes": ["Tầm nhìn"]},
        {"id": "t2", "theme": "Gắn kết",  "sub_themes": ["Nhận thức"]},
    ]
    fake_tool = MagicMock()
    fake_tool.invoke.return_value = fake_themes
    monkeypatch.setattr(m3_design, "suggest_themes", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "qualitative"
    m3_design.M3Agent._render_research_question = "How does TL affect EE?"
    m3_design.M3Agent._render_gaps_summary = ""
    hint = agent.render_hint_for_field("themes")
    assert hint is not None
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "themes"
    assert hint["allow_nested"] is True
    assert len(hint["initial_items"]) == 2
    assert hint["initial_items"][0]["text"].startswith("Lãnh đạo")
    assert hint["initial_items"][0]["sub_items"][0]["text"] == "Tầm nhìn"


def test_purposive_criteria_returns_flat_list_editor(monkeypatch):
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = {
        "criteria": ["At SME", "6mo+ tenure", "Has manager"],
        "strategies": ["Snowball"], "saturation_min": 10, "saturation_max": 15,
    }
    monkeypatch.setattr(m3_design, "suggest_purposive_criteria", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "qualitative"
    m3_design.M3Agent._render_research_question = "x"
    hint = agent.render_hint_for_field("purposive_criteria")
    assert hint["widget_type"] == "list_editor"
    assert hint["allow_nested"] is False
    assert len(hint["initial_items"]) == 3


def test_conceptual_model_returns_list_editor_with_path_adapter(monkeypatch):
    """build_conceptual_model returns {constructs, paths: [{from,to,hypothesis}]};
    the agent adapts paths into ListItem rows (one row per path)."""
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = {
        "constructs": ["TL", "EE", "Trust"],
        "paths": [
            {"from": "TL", "to": "EE", "hypothesis": "H1: TL positively affects EE"},
            {"from": "TL", "to": "Trust", "hypothesis": "H2: TL builds Trust"},
        ],
    }
    monkeypatch.setattr(m3_design, "build_conceptual_model", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "quantitative"
    m3_design.M3Agent._render_research_question = "How does TL affect EE?"
    hint = agent.render_hint_for_field("conceptual_model")
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "conceptual_model"
    assert hint["allow_nested"] is False
    texts = [i["text"] for i in hint["initial_items"]]
    assert any("TL → EE" in t for t in texts)
    assert any("TL → Trust" in t for t in texts)
    assert hint["initial_items"][0]["meta"]["hypothesis"].startswith("H1")
