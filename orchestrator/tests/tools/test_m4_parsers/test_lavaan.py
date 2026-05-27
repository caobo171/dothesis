"""Golden-fixture tests for R lavaan paste-text parser."""
from pathlib import Path

from orchestrator.tools.m4_parsers.lavaan import parse_lavaan


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_lavaan_cfa_extracts_fit_indices():
    text = _load_golden("lavaan_cfa.txt")
    result = parse_lavaan(text, "Confirmatory Factor Analysis (CFI/TLI/RMSEA)")
    assert result is not None
    assert result["parser"] == "regex"
    indices = {row["index"]: row["value"] for row in result["table"]}
    assert indices["CFI"] == 0.945
    assert indices["TLI"] == 0.932
    assert indices["RMSEA"] == 0.057
    assert indices["SRMR"] == 0.054


def test_lavaan_cfa_threshold_check():
    """CFI ≥ 0.90, TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08 — all met in fixture."""
    text = _load_golden("lavaan_cfa.txt")
    result = parse_lavaan(text, "Confirmatory Factor Analysis (CFI/TLI/RMSEA)")
    assert result["thresholds_met"] is True


def test_lavaan_unknown_step_returns_none():
    assert parse_lavaan("text", "Some unknown step") is None
