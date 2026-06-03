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


def test_design_card_grid_for_qualitative_paradigm(monkeypatch):
    """Qualitative `design` cards come from dynamic LLM gen seeded on the
    qual paradigm — typical options are Thematic / Grounded / Phenomenological /
    Case Study / Other."""
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


def test_design_card_grid_for_quantitative_paradigm(monkeypatch):
    """M3-D: quant `design` used to fall through to free text — users had
    no way to pick Linear regression and were stuck with whatever the LLM
    methodology recommender (almost always PLS-SEM) suggested. Now quant
    `design` ships as a card grid driven by the dynamic LLM generator."""
    cards = [
        {"value": "Linear regression", "label": "Linear regression",
         "description": "One DV, predictors"},
        {"value": "PLS-SEM", "label": "PLS-SEM", "description": "Use SmartPLS"},
        {"value": "Other", "label": "Other / Specify", "description": "Type"},
    ]
    _stub_llm_returning(monkeypatch, cards)
    hint = M3Agent().render_hint_for_field(
        "design", partial={"paradigm": "quantitative"})
    assert hint is not None
    assert hint["field_name"] == "design"
    values = {o["value"] for o in hint["options"]}
    assert "Linear regression" in values


def test_design_card_grid_static_fallback_for_quant_includes_regression(monkeypatch):
    """When the dynamic LLM call returns garbage, the static fallback must
    still surface Linear regression so the user can pick a non-SEM design
    and route the rest of M3 toward SPSS/R-friendly tools."""
    fake = MagicMock()
    fake.invoke.return_value.content = "not json"
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)

    hint = M3Agent().render_hint_for_field(
        "design", partial={"paradigm": "quantitative"})
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert {"Linear regression", "PLS-SEM", "Other"}.issubset(values)


def test_design_card_grid_static_fallback_for_qual_includes_thematic(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = "not json"
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)

    hint = M3Agent().render_hint_for_field(
        "design", partial={"paradigm": "qualitative"})
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert {"Thematic Analysis", "Other"}.issubset(values)


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


def test_mixed_design_type_falls_back_to_static_when_llm_fails(monkeypatch):
    """Same bug as M1 — when _generate_card_options times out / returns junk,
    the literal-bounded mixed_design_type must still render its two schema
    values + Other instead of the agent promising cards that never show up."""
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.invoke.return_value.content = "garbage not-json"
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)

    hint = M3Agent().render_hint_for_field(
        "mixed_design_type", partial={"paradigm": "mixed"})
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert {"sequential_explanatory", "sequential_exploratory",
            "Other"}.issubset(values)


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


def test_conceptual_model_renders_flow_chart_with_nodes_questions_and_edges(monkeypatch):
    """Design merge (per user request 2026-06-02): conceptual_model + scale_items
    used to be two separate widgets — first a flat list of paths, then a second
    bubble asking for Likert items per construct. Splitting them was nonsense
    because the user needs to see structure + measurement together (mirrors
    Survify's AdvanceModelType).

    New behaviour: conceptual_model ships ONE flow_chart widget that carries:
      - nodes: each construct with its suggested Likert questions attached
      - edges: each hypothesis path with effect_type and the natural-language
        hypothesis statement
    The user edits both halves in one place and Confirm emits the merged
    shape; scale_items is no longer a separate schema field.
    """
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_model = MagicMock()
    fake_model.invoke.return_value = {
        "constructs": ["TL", "EE", "Trust"],
        "paths": [
            {"from": "TL", "to": "EE", "hypothesis": "H1: TL positively affects EE"},
            {"from": "TL", "to": "Trust", "hypothesis": "H2: TL builds Trust"},
        ],
    }
    monkeypatch.setattr(m3_design, "build_conceptual_model", fake_model)

    fake_batch = MagicMock()
    fake_batch.invoke.return_value = {
        "TL":    [{"id": "TL1", "text": "My supervisor inspires me."},
                  {"id": "TL2", "text": "My supervisor articulates a clear vision."}],
        "EE":    [{"id": "EE1", "text": "I feel engaged at work."}],
        "Trust": [{"id": "TR1", "text": "I trust my supervisor."}],
    }
    monkeypatch.setattr(m3_design, "suggest_scale_items_batch", fake_batch)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "quantitative"
    m3_design.M3Agent._render_research_question = "How does TL affect EE?"
    m3_design.M3Agent._render_constructs = []
    m3_design.M3Agent._render_conceptual_model = None

    hint = agent.render_hint_for_field("conceptual_model")

    assert hint is not None
    assert hint["widget_type"] == "flow_chart", (
        f"conceptual_model must ship flow_chart (got {hint.get('widget_type')!r})"
    )
    assert hint["field_name"] == "conceptual_model"

    # Nodes — one per construct, each carrying its suggested Likert items.
    node_labels = [n["label"] for n in hint["initial_nodes"]]
    assert node_labels == ["TL", "EE", "Trust"]
    # Match by label so we don't depend on which id scheme the impl picks.
    nodes_by_label = {n["label"]: n for n in hint["initial_nodes"]}
    assert nodes_by_label["TL"]["questions"] == [
        "My supervisor inspires me.",
        "My supervisor articulates a clear vision.",
    ]
    assert nodes_by_label["EE"]["questions"] == ["I feel engaged at work."]

    # Edges — one per hypothesis path, hypothesis text preserved.
    assert len(hint["initial_edges"]) == 2
    edge_texts = {(e["source"], e["target"]): e["hypothesis"]
                  for e in hint["initial_edges"]}
    # Source/target reference node ids, not labels — resolve via the node map.
    id_by_label = {n["label"]: n["id"] for n in hint["initial_nodes"]}
    assert edge_texts[(id_by_label["TL"], id_by_label["EE"])].startswith("H1")
    assert edge_texts[(id_by_label["TL"], id_by_label["Trust"])].startswith("H2")
    # Default effect_type is positive — user can flip on the canvas if needed.
    assert all(e.get("effect_type") == "positive" for e in hint["initial_edges"])

    # ONE batched LLM call for ALL constructs (regression-guard for the
    # 'typing dots forever' bug that the prior N-sequential design caused).
    assert fake_batch.invoke.call_count == 1
    assert fake_batch.invoke.call_args[0][0]["constructs"] == ["TL", "EE", "Trust"]
