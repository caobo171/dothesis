"""Tests for dispatch_parse + format_step_as_markdown in m4_parsers/__init__.py."""
from unittest.mock import MagicMock


def test_format_step_as_markdown_with_table():
    from orchestrator.tools.m4_parsers import format_step_as_markdown
    sr = {
        "step_name": "Reliability",
        "table": [{"construct": "TL", "alpha": 0.84}],
        "interpretation": "Reliable.",
    }
    md = format_step_as_markdown(sr)
    assert "**Reliability**" in md
    assert "| construct | alpha |" in md
    assert "TL" in md
    assert "Reliable." in md


def test_format_step_as_markdown_without_table():
    from orchestrator.tools.m4_parsers import format_step_as_markdown
    sr = {"step_name": "Summary", "interpretation": "Done."}
    md = format_step_as_markdown(sr)
    assert "**Summary**" in md
    assert "Done." in md
    assert "|" not in md  # no table when rows are empty


def test_dispatch_parse_unknown_type_uses_llm_fallback(monkeypatch):
    """For data_type with no regex parser registered, dispatch falls through to LLM."""
    from orchestrator.tools.m4_parsers import dispatch_parse

    fake_llm_tool = MagicMock()
    fake_llm_tool.invoke.return_value = {
        "step_name": "x", "table": [], "interpretation": "via llm",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback.extract_step_data",
        fake_llm_tool,
    )
    result = dispatch_parse("Unknown", "some text", "x")
    assert result["parser"] == "llm_fallback"
