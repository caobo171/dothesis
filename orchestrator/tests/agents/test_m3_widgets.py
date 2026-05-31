"""Tests for M3Agent.render_hint_for_field — dynamic cards + paradigm gating + list editors."""
import json
from unittest.mock import MagicMock

from orchestrator.agents.m3_design import M3Agent


def _stub_llm_returning(monkeypatch, cards):
    """Patch M3Agent._get_llm so the dynamic card generator returns `cards`."""
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(cards)
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)
    return fake


def test_tool_returns_card_grid_for_quant(monkeypatch):
    """`tool` is opted into card rendering and the LLM-supplied cards round-trip."""
    cards = [
        {"value": "SmartPLS", "label": "SmartPLS", "description": "PLS-SEM"},
        {"value": "AMOS",     "label": "AMOS",     "description": "CB-SEM"},
        {"value": "Other",    "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M3Agent().render_hint_for_field("tool", partial={"paradigm": "quantitative"})

    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "tool"
    assert hint["title"].startswith("Which analysis tool")
    assert [o["value"] for o in hint["options"]] == ["SmartPLS", "AMOS", "Other"]


def test_tool_returns_card_grid_for_qual(monkeypatch):
    """Same field — different paradigm → LLM is free to suggest qual-aligned tools."""
    cards = [
        {"value": "NVivo",   "label": "NVivo",   "description": "Qual coding"},
        {"value": "MAXQDA",  "label": "MAXQDA",  "description": "Qual analysis"},
        {"value": "Other",   "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M3Agent().render_hint_for_field("tool", partial={"paradigm": "qualitative"})

    assert {o["value"] for o in hint["options"]} == {"NVivo", "MAXQDA", "Other"}


def test_design_card_grid_only_for_qual_paradigm(monkeypatch):
    """`design` is qual-only. Quant skips the card grid and uses free-text input
    so recommend_methodology can drive the conversation."""
    cards = [
        {"value": "thematic_analysis", "label": "Thematic Analysis", "description": "Codes → themes"},
        {"value": "grounded_theory",    "label": "Grounded Theory",   "description": "Iterative coding"},
        {"value": "Other",              "label": "Other / Specify",   "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    agent = M3Agent()
    hint = agent.render_hint_for_field("design", partial={"paradigm": "qualitative"})
    assert hint is not None
    assert hint["field_name"] == "design"
    assert hint["title"].startswith("Which qualitative design")

    # Quant paradigm → no card grid.
    assert agent.render_hint_for_field("design", partial={"paradigm": "quantitative"}) is None
    # Empty partial (paradigm not yet set) → also no card grid.
    assert agent.render_hint_for_field("design", partial={}) is None


def test_mixed_design_type_returns_card_grid(monkeypatch):
    """`mixed_design_type` is only asked when paradigm is mixed; LLM picks the
    sequential_* variants the schema accepts."""
    cards = [
        {"value": "sequential_explanatory", "label": "Sequential Explanatory",
         "description": "Quant first, qual explains"},
        {"value": "sequential_exploratory", "label": "Sequential Exploratory",
         "description": "Qual first, quant tests"},
        {"value": "Other", "label": "Other / Specify", "description": "Type your own"},
    ]
    _stub_llm_returning(monkeypatch, cards)

    hint = M3Agent().render_hint_for_field("mixed_design_type", partial={"paradigm": "mixed"})

    assert hint["widget_type"] == "card_grid"
    values = {o["value"] for o in hint["options"]}
    assert {"sequential_explanatory", "sequential_exploratory"}.issubset(values)


def test_card_generation_falls_back_to_none_when_llm_fails(monkeypatch):
    """Card branches must not crash on LLM/JSON failure — falls back to free-text."""
    fake = MagicMock()
    fake.invoke.side_effect = RuntimeError("network down")
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)

    assert M3Agent().render_hint_for_field("tool", partial={"paradigm": "quantitative"}) is None


def test_sampling_strategy_returns_card_grid_with_common_strategies():
    """W6: sampling_strategy used to fall through to free text. Now ships as a
    card_grid of the standard non-probability + probability strategies plus
    an Other escape hatch — keeps the user one click away from a final
    answer instead of needing to remember the right academic term."""
    agent = M3Agent()
    hint = agent.render_hint_for_field("sampling_strategy",
                                       partial={"paradigm": "quantitative"})
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "sampling_strategy"
    values = {o["value"] for o in hint["options"]}
    assert {"convenience", "purposive", "snowball", "random",
            "Other"}.issubset(values)


def test_target_sample_size_returns_card_grid_with_common_sizes():
    """W6: target_sample_size — common thesis-sized samples + Other-Specify.
    Cohen's rules of thumb (n=30 small, n=100 medium, n=200 SEM minimum,
    n=384 95%CI ±5%) cover ~85% of real choices; Other lets the user type
    any custom number."""
    agent = M3Agent()
    hint = agent.render_hint_for_field("target_sample_size",
                                       partial={"paradigm": "quantitative"})
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "target_sample_size"
    values = {o["value"] for o in hint["options"]}
    # Common sizes + Other. Specific numbers are documented in the impl.
    assert "Other" in values
    assert len([v for v in values if v.isdigit()]) >= 3


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
