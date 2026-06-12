"""run_stats — whitelisted ops produce real numbers; non-ops are rejected."""
import json

import pytest

pd = pytest.importorskip("pandas")

from agent.tools.stats import run_stats


@pytest.fixture
def csv(tmp_path):
    # Deterministic toy data: y correlates strongly with x1, weakly with x2.
    rows = 40
    x1 = [i / 10 for i in range(rows)]
    x2 = [(i % 7) / 7 for i in range(rows)]
    y = [0.8 * a + 0.1 * b + 1.0 for a, b in zip(x1, x2)]
    df = pd.DataFrame({
        "x1": x1, "x2": x2, "y": y,
        "item1": x1, "item2": [v + 0.05 for v in x1], "item3": [v - 0.03 for v in x1],
        "group": ["a" if i % 2 else "b" for i in range(rows)],
    })
    p = tmp_path / "data.csv"
    df.to_csv(p, index=False)
    return str(p)


def _run(op, file, params=None):
    return json.loads(run_stats.func(op, file, params))


def test_non_whitelisted_op_rejected(csv):
    out = _run("eval_python", csv)
    assert out["error"].startswith("op 'eval_python' is not whitelisted")
    assert "detect" in out["available"]


def test_detect_returns_schema_not_data(csv):
    out = _run("detect", csv)
    assert out["rows"] == 40
    names = [c["name"] for c in out["columns"]]
    assert "y" in names and "group" in names
    # Schema only — no row dumps.
    assert "data" not in out


def test_cronbach_high_for_parallel_items(csv):
    out = _run("cronbach", csv, {"items": ["item1", "item2", "item3"]})
    assert out["alpha"] > 0.9


def test_regression_recovers_coefficients(csv):
    out = _run("regression", csv, {"y": "y", "x": ["x1", "x2"]})
    assert out["r2"] > 0.99
    assert abs(out["coefficients"]["x1"]["beta"] - 0.8) < 0.01
    assert out["coefficients"]["x1"]["p"] < 0.001


def test_ttest_runs(csv):
    out = _run("ttest", csv, {"value": "y", "group": "group"})
    assert "t" in out and "p" in out
    assert set(out["groups"]) == {"a", "b"}


def test_missing_file_is_clean_error(tmp_path):
    out = _run("describe", str(tmp_path / "nope.csv"))
    assert "failed" in out["error"]
