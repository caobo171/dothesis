"""run_stats provenance capture (roadmap #12, Task 2.3) + state key (2.4)."""
import json

import numpy as np
import pandas as pd
import pytest

from agent.tools.stats import run_stats
from agent.provenance import load_ledger_rows


@pytest.fixture
def csv(tmp_path):
    p = tmp_path / "d.csv"
    rng = np.random.default_rng(0)
    pd.DataFrame({"a": rng.normal(0, 1, 30), "b": rng.normal(0, 1, 30)}).to_csv(p, index=False)
    return str(p), tmp_path


def _run(op, file, params=None):
    return json.loads(run_stats.func(op, file, params))


def test_successful_op_appends_one_row(csv):
    path, tmp = csv
    out = _run("describe", path)
    assert "error" not in out
    rows = load_ledger_rows(str(tmp))
    assert len(rows) == 1
    assert rows[0]["op"] == "describe" and rows[0]["dataset"]["rows"] == 30
    assert len(rows[0]["dataset"]["sha256"]) == 64


def test_error_op_appends_nothing(csv):
    path, tmp = csv
    _run("nonexistent_op", path)
    assert load_ledger_rows(str(tmp)) == []


def test_fileless_op_appends_nothing(tmp_path):
    _run("power", "", {"analysis": "regression", "mode": "a_priori", "f2": 0.15,
                       "n_predictors": 3, "power": 0.8})
    assert load_ledger_rows(str(tmp_path)) == []


def test_capture_records_validation(csv, monkeypatch):
    path, tmp = csv
    # force a soft validation finding via a monkeypatched validator
    import agent.stats_validation as sv
    monkeypatch.setattr(sv, "validate_run_stats",
                        lambda op, r: {"passed": True, "hard": 0, "soft": 1,
                                       "findings": [{"check": "x", "severity": "soft"}]})
    _run("describe", path)
    rows = load_ledger_rows(str(tmp))
    assert rows[0]["validation"]["soft"] == 1


def test_capture_fail_open(csv, monkeypatch):
    path, tmp = csv
    import agent.provenance as prov
    monkeypatch.setattr(prov, "append_ledger_row",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    out = _run("describe", path)
    assert "error" not in out  # op still returns normally


def test_ledger_touched_only_in_wrapper():
    import inspect
    import agent.tools.stats as st
    # No _op_* function body references the ledger — capture lives only in the
    # run_stats wrapper (the whitelist-is-the-boundary posture).
    for name, fn in vars(st).items():
        if name.startswith("_op_") and callable(fn):
            assert "append_ledger_row" not in inspect.getsource(fn)
            assert "stats_provenance" not in inspect.getsource(fn)


# --- Task 2.4: state key ----------------------------------------------------

def test_analysis_provenance_ownership_and_non_content():
    from agent.state import SLICE_OWNERSHIP, NON_CONTENT_KEYS
    assert "analysis_provenance" in SLICE_OWNERSHIP["M4"]
    assert "analysis_provenance" in NON_CONTENT_KEYS
