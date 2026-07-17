"""Provenance ledger (roadmap #12, phase 2) — row builder, sidecar, matcher."""
import hashlib
import json
import subprocess
import sys

import pytest

from agent.provenance import (
    append_ledger_row, build_ledger_row, dataset_fingerprint, ledger_pruned,
    load_ledger_rows, match_claims,
)


# --- import purity ----------------------------------------------------------

def test_import_purity():
    code = "import sys, agent.provenance; assert 'langchain' not in sys.modules; print('ok')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


# --- Task 2.1: row builder --------------------------------------------------

def test_dataset_fingerprint(tmp_path):
    p = tmp_path / "d.csv"
    p.write_bytes(b"a,b\n1,2\n")
    fp = dataset_fingerprint(str(p), rows=1, cols=2)
    assert fp["sha256"] == hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    assert fp["rows"] == 1 and fp["cols"] == 2
    assert dataset_fingerprint(str(tmp_path / "nope.csv")) is None


def test_build_row_values_and_digests():
    summary = {"paths": {"TRUST -> INT": {"beta": -0.31}},
               "reliability": {"TRUST": {"ave": 0.62}},
               "validation": {"passed": True, "hard": 0, "soft": 1}}
    row = build_ledger_row("pls_sem", {"bootstrap_samples": 500}, summary, None, seq=1)
    assert row["op"] == "pls_sem" and row["seq"] == 1
    metrics = {t[0] for t in row["values"]}
    assert "beta" in metrics and "ave" in metrics
    assert row["validation"] == {"passed": True, "hard": 0, "soft": 1}
    assert len(row["params_fp"]) == 12 and len(row["result_digest"]) == 12
    assert row["engine"].startswith("thesis_stats")


def test_attest_power():
    s = {"mode": "a_priori", "analysis": "pls_sem", "required_n": 160,
         "justification": "x" * 500}
    row = build_ledger_row("power", {}, s, None, 1)
    assert row["attest"]["required_n"] == 160
    assert len(row["attest"]["justification"]) == 300


def test_attest_method_advice():
    s = {"recommendation": [{"method": "pls_sem", "rank": 1}],
         "conflict_with_choice": {"reasons": ["a", "b"]}, "inputs_fingerprint": "sha1:xx"}
    row = build_ledger_row("method_advice", {}, s, None, 1)
    assert row["attest"]["conflicts"] == 2 and row["attest"]["top"]["method"] == "pls_sem"


def test_row_determinism_minus_ts_seq():
    s = {"reliability": {"X": {"ave": 0.6}}}
    a = build_ledger_row("pls_sem", {}, s, None, 1)
    b = build_ledger_row("pls_sem", {}, s, None, 1)
    for r in (a, b):
        del r["ts"]
    assert a == b


# --- Task 2.2: sidecar ------------------------------------------------------

def test_append_assigns_seq(tmp_path):
    d = tmp_path / "data.csv"
    d.write_text("x\n1\n")
    assert append_ledger_row(str(d), {"op": "describe", "values": []})
    assert append_ledger_row(str(d), {"op": "corr", "values": []})
    rows = load_ledger_rows(str(tmp_path))
    assert [r["seq"] for r in rows] == [1, 2]


def test_cap_prunes_oldest(tmp_path):
    from agent.provenance import _MAX_ROWS
    d = tmp_path / "data.csv"
    d.write_text("x\n")
    for i in range(_MAX_ROWS + 1):
        append_ledger_row(str(d), {"op": "describe", "values": []})
    rows = load_ledger_rows(str(tmp_path))
    assert len(rows) == _MAX_ROWS and ledger_pruned(rows)


def test_corrupt_line_skipped(tmp_path):
    from agent.provenance import _sidecar_path
    d = tmp_path / "data.csv"
    d.write_text("x\n")
    sc = _sidecar_path(str(d))
    sc.write_text('{"seq": 1, "op": "describe", "values": []}\nGARBAGE NOT JSON\n')
    append_ledger_row(str(d), {"op": "corr", "values": []})
    rows = load_ledger_rows(str(tmp_path))
    assert len(rows) == 2 and rows[-1]["op"] == "corr"


def test_load_bounded(tmp_path, monkeypatch):
    # a deep decoy tree does not blow up (depth bound)
    deep = tmp_path
    for i in range(6):
        deep = deep / f"l{i}"
        deep.mkdir()
    (deep / "stats_provenance.jsonl").write_text('{"seq":1,"op":"x","values":[]}\n')
    assert load_ledger_rows(str(tmp_path)) == []  # beyond depth 3


# --- Task 2.5: matcher ------------------------------------------------------

def _claim(metric, value, path=None, construct=None, table="structural_model", **flags):
    return {"metric": metric, "value": value, "table": table,
            "unit": {"construct": construct, "item": None, "path": path}, **flags}


def _row(values, seq=1, op="pls_sem"):
    return {"seq": seq, "op": op, "dataset": {"file": "d.csv", "sha256": "a" * 64,
            "rows": 200, "cols": 10}, "values": values}


def test_match_computed_by_path():
    ledger = [_row([["beta", -0.31, "TRUST -> INT"]])]
    claims = [_claim("beta", -0.31, path="TRUST -> INT")]
    s = match_claims(claims, ledger)
    assert s["coverage"]["computed"] == 1 and s["ledger"]["seqs_matched"] == [1]


def test_match_precision_2dp_vs_4dp():
    ledger = [_row([["ave", 0.6234, "TRUST"]])]
    claims = [_claim("ave", 0.62, construct="TRUST")]  # parsed 2dp
    assert match_claims(claims, ledger)["coverage"]["computed"] == 1


def test_unit_discipline_no_cross_path_match():
    ledger = [_row([["beta", 0.4, "A -> B"]])]
    claims = [_claim("beta", 0.4, path="C -> D")]  # same value, different path
    s = match_claims(claims, ledger)
    assert s["coverage"]["computed"] == 0 and s["coverage"]["validated"] == 1


def test_p_never_value_matched():
    ledger = [_row([["p", 0.05, None]])]
    claims = [_claim("p", 0.05, path=None, table="structural_model")]
    # p is forbidden from value-only matching → validated, not computed
    assert match_claims(claims, ledger)["coverage"]["computed"] == 0


def test_unchecked_and_summary_bounds():
    claims = [_claim("beta", "not a number", path="X -> Y")]
    s = match_claims(claims, [])
    assert s["coverage"]["unchecked"] == 1
    assert len(json.dumps(s)) < 4096


def test_datasets_deduped():
    ledger = [_row([["ave", 0.6, "X"]], seq=1), _row([["ave", 0.7, "Y"]], seq=2)]
    s = match_claims([_claim("ave", 0.6, construct="X")], ledger)
    assert len(s["datasets"]) == 1 and s["datasets"][0]["sha256_12"] == "a" * 12
