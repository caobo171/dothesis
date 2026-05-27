"""Tests for M4Agent render_hint_for_field — emits ListEditorHint for outline fields."""
from orchestrator.agents.m4_analysis import M4Agent


def test_analysis_outline_returns_list_editor_for_spss():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    hint = agent.render_hint_for_field("analysis_outline")
    assert hint is not None
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "analysis_outline"
    assert hint["allow_nested"] is False
    step_names = [i["text"] for i in hint["initial_items"]]
    assert "Descriptive Statistics" in step_names
    assert "Reliability (Cronbach's Alpha)" in step_names


def test_analysis_outline_returns_list_editor_for_smartpls():
    agent = M4Agent()
    M4Agent._render_outline_type = "SmartPLS"
    hint = agent.render_hint_for_field("analysis_outline")
    step_names = [i["text"] for i in hint["initial_items"]]
    assert "Outer Loadings" in step_names
    assert "Path Coefficients (Bootstrap 5000)" in step_names


def test_analysis_outline_returns_list_editor_for_qualitative():
    agent = M4Agent()
    M4Agent._render_outline_type = "Qualitative"
    hint = agent.render_hint_for_field("analysis_outline")
    step_names = [i["text"] for i in hint["initial_items"]]
    assert any("coding" in s.lower() or "code" in s.lower() for s in step_names)
    assert any("theme" in s.lower() for s in step_names)


def test_outline_quant_and_outline_qual_emit_list_editor_for_mixed():
    agent = M4Agent()
    M4Agent._render_outline_type = "Mixed"
    M4Agent._render_paradigm = "mixed"
    h1 = agent.render_hint_for_field("outline_quant")
    assert h1 is not None and h1["widget_type"] == "list_editor"
    h2 = agent.render_hint_for_field("outline_qual")
    assert h2 is not None and h2["widget_type"] == "list_editor"


def test_data_paste_returns_none():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    for f in ("data_paste", "data_paste_quant", "data_paste_qual"):
        assert agent.render_hint_for_field(f) is None


def test_pseudo_fields_return_none():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    for f in ("_run_execution", "_run_qual_pipeline", "_summary"):
        assert agent.render_hint_for_field(f) is None
