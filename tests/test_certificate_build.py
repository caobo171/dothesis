"""Committee-readiness certificate assembler (roadmap #12) — pure, offline."""
import copy
import json
import subprocess
import sys

import pytest

from quality.certificate import (
    build_certificate, build_checklist, gate_summary, render_certificate_md,
)


def _stub_judge(monkeypatch):
    import orchestrator.tools.m5_writing as _m5
    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: (_ for _ in ()).throw(RuntimeError("no LLM in certificate")))


DIRTY = {
    "m2_literature": {"literature_sources": [{"title": "Real", "authors": "A", "year": 2020}]},
    "m3_design": {"methodology": "PLS-SEM", "hypotheses": ["H1"]},
    "m4_analysis": {"analysis_results": {
        "measurement_model": [{"construct": "X", "items": [{"item": "x1", "loading": 0.9},
                                                           {"item": "x2", "loading": 0.9}], "ave": 0.20}],
        "hypothesis_tests": [{"id": "H1", "path": "X->Y", "decision": "supported",
                              "numbers": {"beta": 0.34, "p": 0.001}}]}},
    "m5_writing": {"final_sections": [{"title": "results",
        "prose": "H1 confirmed with a strong effect (beta = .34) per (Ghost, 2099), "
                 "a clearly adequate and detailed result for the committee here."}]},
}

CLEAN = {
    "m1_topic": {"research_title": "A Study", "research_questions": ["RQ1"]},
    "m2_literature": {"literature_sources": [{"title": "Real", "authors": "A", "year": 2020}]},
    "m3_design": {"methodology": "PLS-SEM"},
    "m4_analysis": {"analysis_results": {"descriptives": {"n": 220}}},
}


# --- import purity ----------------------------------------------------------

def test_import_purity():
    code = ("import sys, quality.certificate; "
            "assert 'langchain' not in sys.modules; print('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


# --- Task 1.2: checklist ----------------------------------------------------

def test_checklist_eleven_items_fixed_order(monkeypatch):
    _stub_judge(monkeypatch)
    cert = build_certificate(DIRTY)
    ids = [it["id"] for it in cert["checklist"]]
    assert ids == ["rq_hypothesis_trace", "sources_verified", "citation_integrity",
                   "method_justified", "power_defended", "screening_documented",
                   "measurement_model_reported", "hypotheses_decided", "chapters_coherent",
                   "similarity_selfchecked", "defense_drilled"]
    for it in cert["checklist"]:
        assert it["status"] in ("pass", "warn", "fail", "not_checked")


def test_citation_integrity_fails_on_ghost(monkeypatch):
    _stub_judge(monkeypatch)
    cert = build_certificate(DIRTY)
    ci = next(it for it in cert["checklist"] if it["id"] == "citation_integrity")
    assert ci["status"] == "fail"


def test_measurement_model_fails_on_hard_ave(monkeypatch):
    _stub_judge(monkeypatch)
    mm = next(it for it in build_certificate(DIRTY)["checklist"]
              if it["id"] == "measurement_model_reported")
    assert mm["status"] == "fail"  # AVE 0.20 vs mean λ² 0.81


def test_similarity_never_fails(monkeypatch):
    _stub_judge(monkeypatch)
    sim = next(it for it in build_certificate(DIRTY)["checklist"]
               if it["id"] == "similarity_selfchecked")
    assert sim["status"] != "fail"


def test_defense_always_not_checked(monkeypatch):
    _stub_judge(monkeypatch)
    d = next(it for it in build_certificate(CLEAN)["checklist"] if it["id"] == "defense_drilled")
    assert d["status"] == "not_checked" and d["limitations"]


def test_screening_no_dataset_is_not_checked_not_fail(monkeypatch):
    _stub_judge(monkeypatch)
    sc = next(it for it in build_certificate(CLEAN)["checklist"]
              if it["id"] == "screening_documented")
    assert sc["status"] == "not_checked"


# --- Task 1.3: build_certificate --------------------------------------------

def test_certificate_schema(monkeypatch):
    _stub_judge(monkeypatch)
    cert = build_certificate(CLEAN, project_id="p1")
    assert cert["schema_version"] == 1 and cert["kind"] == "dothesis.certificate"
    assert cert["thesis"]["method"] == "pls-sem"
    assert set(cert) >= {"readiness", "checklist", "provenance", "advisory",
                         "limitations", "attestation", "content_sha256"}


def test_readiness_ready_iff_no_blocking_no_fail(monkeypatch):
    _stub_judge(monkeypatch)
    assert build_certificate(CLEAN)["readiness"]["status"] == "ready"
    assert build_certificate(DIRTY)["readiness"]["status"] == "not_ready"


def test_mandatory_honesty_strings(monkeypatch):
    _stub_judge(monkeypatch)
    blob = json.dumps(build_certificate(CLEAN))
    assert "NOT a Turnitin scan" in blob
    assert "CrossRef only" in blob
    assert "checked for internal consistency only" in blob
    assert "not cryptographically signed" in blob
    assert "Defense-drill completion is not yet recorded" in blob


def test_provenance_passthrough_and_empty(monkeypatch):
    _stub_judge(monkeypatch)
    assert build_certificate(CLEAN)["provenance"]["numbers"]["total"] == 0
    withprov = copy.deepcopy(CLEAN)
    withprov["m4_analysis"]["analysis_provenance"] = {
        "numbers": {"total": 5, "computed": 3, "validated": 2, "unchecked": 0},
        "ledger": {"pruned": False}, "ops_seen": {"power": {}}}
    cert = build_certificate(withprov)
    assert cert["provenance"]["numbers"]["computed"] == 3
    assert next(it for it in cert["checklist"] if it["id"] == "power_defended")["status"] == "pass"


def test_determinism_and_sha(monkeypatch):
    _stub_judge(monkeypatch)
    a = build_certificate(CLEAN)
    b = build_certificate(CLEAN)
    del a["generated_at"], b["generated_at"]
    assert a == b
    # sha recomputes over the cert minus content_sha256 + generated_at
    from quality.certificate import _sha256_of
    src = {k: v for k, v in b.items() if k not in ("content_sha256", "generated_at")}
    assert b["content_sha256"] == _sha256_of(src)


def test_never_raises_on_garbage(monkeypatch):
    _stub_judge(monkeypatch)
    cert = build_certificate({"m4_analysis": "not a dict"})
    assert cert["readiness"]["status"] in ("ready", "not_ready")


def test_rubric_crash_degrades(monkeypatch):
    import quality.certificate as C
    monkeypatch.setattr("quality.rubric.score_thesis",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    cert = build_certificate(CLEAN)
    assert cert["readiness"]["status"] == "not_ready" and cert["content_sha256"]


def test_judge_rubric_injection_does_not_change_readiness(monkeypatch):
    _stub_judge(monkeypatch)
    from quality.rubric import score_thesis
    det = build_certificate(CLEAN)
    # inject a full rubric with a judge dim
    full = score_thesis(CLEAN, include_judge=False)
    full["dimensions"].append({"name": "methodology", "weight": 0.15, "score": 0.3,
                               "findings": [{"issue": "weak", "severity": "soft", "fix": "-", "chapter": "-"}]})
    withjudge = build_certificate(CLEAN, rubric=full)
    assert withjudge["readiness"]["status"] == det["readiness"]["status"]
    assert withjudge["advisory"]["judge_dimensions"] is not None
    det_status = {it["id"]: it["status"] for it in det["checklist"]}
    inj_status = {it["id"]: it["status"] for it in withjudge["checklist"]}
    assert det_status == inj_status


# --- Task 1.4: gate_summary -------------------------------------------------

def test_gate_summary_shape_and_bound(monkeypatch):
    _stub_judge(monkeypatch)
    gs = gate_summary(build_certificate(DIRTY, project_id="p1"))
    assert gs["deterministic"] is True and len(gs["items"]) == 11
    assert gs["ready"] is False
    assert len(json.dumps(gs)) < 2048
    assert gs["certificate"]["content_sha256"]


def test_gate_summary_ready_mirrors(monkeypatch):
    _stub_judge(monkeypatch)
    assert gate_summary(build_certificate(CLEAN))["ready"] is True


# --- Task 1.5: render -------------------------------------------------------

def test_render_deterministic_and_leads_with_pass(monkeypatch):
    _stub_judge(monkeypatch)
    cert = build_certificate(CLEAN)
    a = render_certificate_md(cert)
    b = render_certificate_md(cert)
    assert a == b
    assert "# DoThesis Verification Report" in a
    assert "NOT a Turnitin scan" in a
    assert len(a) < 8000


def test_render_not_checked_no_fail_word(monkeypatch):
    _stub_judge(monkeypatch)
    # a mostly not_checked cert must not render the word "fail" for those rows
    md = render_certificate_md(build_certificate({}))
    for line in md.splitlines():
        if "not checked" in line:
            assert "fail" not in line.lower()


def test_certificate_attests_all_gates_ran(monkeypatch):
    _stub_judge(monkeypatch)
    import copy as _c
    cs = _c.deepcopy(CLEAN)
    cs["m4_analysis"]["analysis_provenance"] = {
        "numbers": {"total": 3, "computed": 3, "validated": 0, "unchecked": 0},
        "ledger": {"pruned": False}, "ops_seen": {}, "gate": {"stats_validation": "ran", "policy": "strict"}}
    cert = build_certificate(cs)
    assert "verification gate ran" in cert["attestation"]


def test_certificate_notes_gate_unavailable(monkeypatch):
    _stub_judge(monkeypatch)
    import copy as _c
    cs = _c.deepcopy(CLEAN)
    cs["m4_analysis"]["analysis_provenance"] = {
        "numbers": {"total": 1, "computed": 0, "validated": 1, "unchecked": 0},
        "ledger": {"pruned": False}, "gate": {"stats_validation": "unavailable", "policy": "advisory"}}
    assert "verification gate did not run" in build_certificate(cs)["attestation"]


def test_certificate_degrades_without_gate_field(monkeypatch):
    _stub_judge(monkeypatch)
    # legacy state with no gate field → no gate clause, schema still v1
    cert = build_certificate(CLEAN)
    assert cert["schema_version"] == 1
    assert "verification gate ran" not in cert["attestation"]
    assert "verification gate did not run" not in cert["attestation"]
