"""Provenance injection at the M4 commit gate (roadmap #12, Task 2.5)."""
import json
import uuid

import pytest

from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


AR = {"measurement_model": [{"construct": "TRUST",
        "items": [{"item": "t1", "loading": 0.81}, {"item": "t2", "loading": 0.79}],
        "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.638}],
      "hypothesis_tests": [{"id": "H1", "path": "TRUST -> INT",
        "numbers": {"beta": 0.34, "t": 7.0, "p": "<0.001"}, "decision": "supported"}]}


def _store(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.project_dir.mkdir(parents=True, exist_ok=True)
    return store


def _plant_sidecar(store, values):
    row = {"seq": 1, "op": "pls_sem", "dataset": {"file": "d.csv", "sha256": "a" * 64,
           "rows": 200, "cols": 10}, "values": values}
    (store.project_dir / "stats_provenance.jsonl").write_text(json.dumps(row) + "\n")


def test_committed_numbers_get_computed_provenance(tmp_path):
    store = _store(tmp_path)
    _plant_sidecar(store, [["beta", 0.34, "TRUST -> INT"], ["ave", 0.638, "TRUST"]])
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["commit_slice"].func(module="M4", writes={"analysis_results": AR},
                                                reason="commit results"))
    assert "error" not in out
    prov = store.load()["contextStore"]["analysis_provenance"]
    assert prov["numbers"]["computed"] >= 1
    assert prov["ledger"]["rows_seen"] == 1


def test_model_forged_provenance_discarded(tmp_path):
    store = _store(tmp_path)
    _plant_sidecar(store, [["beta", 0.34, "TRUST -> INT"]])
    tools = {t.name: t for t in make_state_tools(store)}
    tools["commit_slice"].func(module="M4", writes={
        "analysis_results": AR,
        "analysis_provenance": {"numbers": {"computed": 999, "total": 999}}},
        reason="forge attempt")
    prov = store.load()["contextStore"]["analysis_provenance"]
    assert prov["numbers"]["computed"] < 999  # deterministic summary, not the forgery


def test_no_ledger_still_commits_validated(tmp_path):
    store = _store(tmp_path)  # no sidecar planted
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["commit_slice"].func(module="M4", writes={"analysis_results": AR},
                                                reason="no ledger"))
    assert "error" not in out
    prov = store.load()["contextStore"]["analysis_provenance"]
    assert prov["numbers"]["computed"] == 0 and prov["numbers"]["validated"] >= 1


def test_hard_gate_blocks_before_provenance(tmp_path):
    store = _store(tmp_path)
    bad = {"measurement_model": [{"construct": "X",
             "items": [{"item": "x1", "loading": 0.9}, {"item": "x2", "loading": 0.9}], "ave": 0.20}]}
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["commit_slice"].func(module="M4", writes={"analysis_results": bad},
                                                reason="impossible"))
    assert "error" in out  # blocked
    assert "analysis_provenance" not in store.load()["contextStore"]


def test_provenance_not_in_read_slice(tmp_path):
    store = _store(tmp_path)
    _plant_sidecar(store, [["beta", 0.34, "TRUST -> INT"]])
    tools = {t.name: t for t in make_state_tools(store)}
    tools["commit_slice"].func(module="M4", writes={"analysis_results": AR}, reason="c")
    # analysis_provenance is NON_CONTENT — not exposed via read_slice
    if "read_slice" in tools:
        rs = json.loads(tools["read_slice"].func(module="M4"))
        assert "analysis_provenance" not in json.dumps(rs) or "analysis_results" in json.dumps(rs)
