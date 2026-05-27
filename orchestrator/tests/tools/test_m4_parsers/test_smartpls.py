"""Golden-fixture tests for SmartPLS paste-text parser."""
from pathlib import Path

from orchestrator.tools.m4_parsers.smartpls import parse_smartpls


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_smartpls_outer_loadings_extracts_per_construct():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Outer Loadings")
    assert result is not None
    assert result["parser"] == "regex"
    by_item = {row["item"]: row for row in result["table"]}
    assert "TL1" in by_item
    assert by_item["TL1"]["loading"] == 0.842
    assert by_item["Trust3"]["loading"] == 0.602  # below 0.7 threshold
    assert by_item["Trust3"]["threshold_met"] is False


def test_smartpls_outer_loadings_flags_below_threshold():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Outer Loadings")
    assert result["thresholds_met"] is False
    assert "Trust3" in result["interpretation"]


def test_smartpls_ave_cr_extracts_validity():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Convergent Validity: AVE & CR")
    assert result is not None
    by_construct = {row["construct"]: row for row in result["table"]}
    assert "TL" in by_construct
    assert by_construct["TL"]["AVE"] == 0.671
    assert by_construct["TL"]["CR"] == 0.890


def test_smartpls_path_coefficients_extracts():
    text = _load_golden("smartpls_paths.txt")
    result = parse_smartpls(text, "Path Coefficients (Bootstrap 5000)")
    assert result is not None
    by_path = {row["path"]: row for row in result["table"]}
    assert "TL -> EE" in by_path
    assert by_path["TL -> EE"]["beta"] == 0.452
    assert by_path["TL -> EE"]["p"] == 0.000
    assert by_path["TL -> EE"]["significant"] is True


def test_smartpls_htmt_extracts_pairs():
    text = _load_golden("smartpls_paths.txt")
    result = parse_smartpls(text, "Discriminant Validity: HTMT & Fornell-Larcker")
    assert result is not None
    pairs = {(row["construct_a"], row["construct_b"]): row["htmt"] for row in result["table"]}
    assert (("EE", "TL") in pairs) or (("TL", "EE") in pairs)


def test_smartpls_unknown_step_returns_none():
    assert parse_smartpls("text", "Some unknown step") is None
