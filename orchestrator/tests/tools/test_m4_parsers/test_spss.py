"""Golden-fixture tests for SPSS paste-text parser."""
from pathlib import Path

import pytest

from orchestrator.tools.m4_parsers.spss import parse_spss


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_spss_cronbach_extracts_constructs_and_alphas():
    text = _load_golden("spss_cronbach.txt")
    result = parse_spss(text, "Reliability (Cronbach's Alpha)")
    assert result is not None
    assert result["step_name"] == "Reliability (Cronbach's Alpha)"
    assert result["parser"] == "regex"
    constructs = {row["construct"]: row for row in result["table"]}
    assert "Transformational Leadership (TL)" in constructs
    assert "Trust" in constructs
    assert constructs["Transformational Leadership (TL)"]["alpha"] == 0.840
    assert constructs["Trust"]["alpha"] == 0.620


def test_spss_cronbach_flags_threshold_breach():
    """Trust α=0.62 is below 0.7 → thresholds_met should be False."""
    text = _load_golden("spss_cronbach.txt")
    result = parse_spss(text, "Reliability (Cronbach's Alpha)")
    assert result["thresholds_met"] is False
    assert "below" in result["interpretation"].lower() or "0.7" in result["interpretation"]


def test_spss_regression_extracts_coefficients():
    text = _load_golden("spss_regression.txt")
    result = parse_spss(text, "Regression Analysis")
    assert result is not None
    assert result["step_name"] == "Regression Analysis"
    # At least two predictors (TL, Trust) + R² found
    table_predictors = {row["predictor"] for row in result["table"] if row.get("predictor") != "(Constant)"}
    assert "TL" in table_predictors
    assert "Trust" in table_predictors


def test_spss_unknown_step_returns_none():
    """Unrecognized step name → None (signals fallback to LLM)."""
    result = parse_spss("any text", "Some unknown step")
    assert result is None


def test_spss_empty_text_returns_none():
    assert parse_spss("", "Reliability (Cronbach's Alpha)") is None
