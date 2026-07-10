"""check_thresholds (F8 Task 4): classify pasted result tables against standard
thresholds and flag suspiciously-perfect patterns. It must NEVER compute a new
statistic — only compare values the student already pasted."""
import json

from agent.tools.stats import check_thresholds  # module-level @tool, run_stats sibling


def test_htmt_above_085_flagged():
    out = json.loads(check_thresholds.func(table_kind="htmt",
                     rows=[{"pair": "BI-ATT", "value": 0.91}]))
    assert any("discriminant" in f["issue"].lower() for f in out["findings"])


def test_suspiciously_perfect_loadings_flagged():
    out = json.loads(check_thresholds.func(table_kind="loadings",
                     rows=[{"item": f"X{i}", "value": 0.96} for i in range(8)]))
    assert any("suspicious" in f["issue"].lower() or "straight" in f["issue"].lower()
               for f in out["findings"])


def test_good_loadings_no_flags():
    out = json.loads(check_thresholds.func(table_kind="loadings",
                     rows=[{"item": "X1", "value": 0.74}, {"item": "X2", "value": 0.81}]))
    assert out["findings"] == []


def test_low_loading_flagged():
    out = json.loads(check_thresholds.func(table_kind="loadings",
                     rows=[{"item": "X1", "value": 0.55}]))
    assert any("0.708" in f["issue"] or "remov" in f["issue"].lower() for f in out["findings"])


def test_unknown_table_kind_no_crash():
    out = json.loads(check_thresholds.func(table_kind="mystery",
                     rows=[{"item": "X1", "value": 0.5}]))
    assert out["findings"] == [] and out["table_kind"] == "mystery"
