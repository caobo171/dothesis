"""Tests for M4Agent outline-type-aware field walk."""
from orchestrator.agents.m4_analysis import M4Agent


def test_outline_template_key_from_tool_smartpls():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("SmartPLS") == "SmartPLS"
    assert agent._outline_template_key_from_tool("smartpls") == "SmartPLS"


def test_outline_template_key_from_tool_spss():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("SPSS") == "SPSS"
    assert agent._outline_template_key_from_tool("Stata") == "SPSS"


def test_outline_template_key_from_tool_cbsem():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("AMOS") == "CB-SEM"
    assert agent._outline_template_key_from_tool("R lavaan") == "CB-SEM"


def test_outline_template_key_from_tool_qual():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("NVivo") == "Qualitative"
    assert agent._outline_template_key_from_tool("Atlas.ti") == "Qualitative"
    assert agent._outline_template_key_from_tool("Manual") == "Qualitative"


def test_outline_template_key_from_tool_unknown():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool(None) == "Unknown"
    assert agent._outline_template_key_from_tool("Mystery Tool") == "Unknown"


def test_walk_order_spss():
    """SPSS walk: data_paste → analysis_outline → _run_execution → _summary."""
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste"
    partial["data_paste"] = "spss output here"
    assert agent._next_missing_field(partial) == "analysis_outline"
    partial["analysis_outline"] = {"sections": [{"name": "Reliability"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_execution"
    partial["_run_execution_done"] = True
    assert agent._next_missing_field(partial) == "_summary"


def test_walk_order_qualitative():
    agent = M4Agent()
    M4Agent._render_outline_type = "Qualitative"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste"
    partial["data_paste"] = "transcript here"
    assert agent._next_missing_field(partial) == "analysis_outline"
    partial["analysis_outline"] = {"sections": [{"name": "Initial coding"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_qual_pipeline"


def test_walk_order_mixed():
    agent = M4Agent()
    M4Agent._render_outline_type = "Mixed"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste_quant"
    partial["data_paste_quant"] = "x"
    assert agent._next_missing_field(partial) == "outline_quant"
    partial["outline_quant"] = {"sections": [{"name": "x"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_execution"
    partial["_run_execution_done"] = True
    assert agent._next_missing_field(partial) == "data_paste_qual"
