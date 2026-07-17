"""The #1-risk guard (design §10.1): low coverage degrades WORDING, never
correctness. A parse-path thesis (numbers pasted, no ledger) must certify as
truthfully as a compute-path one — computed:0 is honest, not a failure grade."""
import json

import pytest

from quality.certificate import build_certificate, gate_summary


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    import orchestrator.tools.m5_writing as _m5
    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: (_ for _ in ()).throw(RuntimeError("no LLM")))


BASE_AR = {"measurement_model": [{"construct": "X",
             "items": [{"item": "x1", "loading": 0.81}, {"item": "x2", "loading": 0.79}],
             "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.638}],
           "hypothesis_tests": [{"id": "H1", "path": "X -> Y",
             "numbers": {"beta": 0.34, "t": 7.0, "p": "<0.001"}, "decision": "supported"}]}


def _store(provenance=None):
    m4 = {"analysis_results": BASE_AR}
    if provenance is not None:
        m4["analysis_provenance"] = provenance
    return {"m1_topic": {"research_title": "T", "research_questions": ["Q"]},
            "m2_literature": {"literature_sources": [{"title": "Real", "authors": "A", "year": 2020}]},
            "m3_design": {"methodology": "PLS-SEM"}, "m4_analysis": m4}


def test_parse_path_computed_zero_still_honest():
    # No provenance block (numbers were pasted): computed 0 — but still a valid,
    # non-failing certificate carrying every mandatory limitation.
    cert = build_certificate(_store(provenance=None))
    assert cert["provenance"]["numbers"]["computed"] == 0
    blob = json.dumps(cert)
    for s in ("NOT a Turnitin scan", "CrossRef only", "checked for internal consistency only",
              "not cryptographically signed", "Defense-drill completion is not yet recorded"):
        assert s in blob


def test_compute_path_computed_positive():
    prov = {"numbers": {"total": 3, "computed": 3, "validated": 0, "unchecked": 0},
            "ledger": {"pruned": False}, "ops_seen": {"pls_sem": 1}}
    cert = build_certificate(_store(provenance=prov))
    assert cert["provenance"]["numbers"]["computed"] == 3


def test_coverage_does_not_change_readiness():
    # Same numbers, different provenance coverage → identical readiness.
    a = build_certificate(_store(provenance=None))
    b = build_certificate(_store(provenance={
        "numbers": {"total": 3, "computed": 3, "validated": 0, "unchecked": 0},
        "ledger": {"pruned": False}, "ops_seen": {}}))
    assert a["readiness"]["status"] == b["readiness"]["status"]
    # and the checklist statuses match (coverage is not a checklist input except
    # method/power/screening which key off ops_seen, absent in both here)
    assert {i["id"]: i["status"] for i in a["checklist"] if i["id"] not in
            ("method_justified", "power_defended", "screening_documented")} == \
           {i["id"]: i["status"] for i in b["checklist"] if i["id"] not in
            ("method_justified", "power_defended", "screening_documented")}


def test_pruned_ledger_disclosed():
    cert = build_certificate(_store(provenance={
        "numbers": {"total": 3, "computed": 3, "validated": 0, "unchecked": 0},
        "ledger": {"pruned": True}, "ops_seen": {}}))
    assert any("ledger was truncated" in lim for lim in cert["limitations"])
