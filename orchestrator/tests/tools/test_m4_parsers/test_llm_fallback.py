"""Tests for the LLM extraction fallback path."""
import json
from unittest.mock import MagicMock


def test_extract_step_data_returns_structured(monkeypatch):
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "step_name": "EFA",
        "table": [
            {"factor": "F1", "items": 4, "eigenvalue": 3.421},
        ],
        "thresholds_met": True,
        "interpretation": "KMO = 0.812; 4 factors extracted.",
        "parser": "llm_fallback",
    })
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )

    result = extract_step_data.invoke({
        "text": "any SPSS output here",
        "step_name": "EFA",
        "data_type": "SPSS",
    })
    assert result is not None
    assert result["step_name"] == "EFA"
    assert result["table"][0]["factor"] == "F1"
    assert result["parser"] == "llm_fallback"


def test_extract_step_data_returns_none_on_malformed(monkeypatch):
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )

    result = extract_step_data.invoke({
        "text": "x", "step_name": "y", "data_type": "SPSS",
    })
    assert result is None


def test_extract_step_data_forces_llm_fallback_parser_tag(monkeypatch):
    """Even if the LLM returns parser='regex', we override it to llm_fallback."""
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "step_name": "x", "table": [], "interpretation": "",
        "parser": "regex",  # WRONG — the function must overwrite this
    })
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )
    result = extract_step_data.invoke({
        "text": "x", "step_name": "x", "data_type": "SPSS",
    })
    assert result["parser"] == "llm_fallback"
