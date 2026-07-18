"""Committee-readiness certificate — the machine-checkable appendix (roadmap #12).

Assembles everything the shipped chains produce (verified sources, per-number
provenance + self-validation, power, screening, coherence, similarity, method
advice) into ONE bounded, deterministic JSON: an 11-item checklist + a
provenance summary + honest coverage/limitations, plus a <2 KB `gate_summary`
projection for B2B callers and a markdown renderer for the export appendix.

Pure and offline: `build_certificate` makes ZERO LLM calls by default
(`include_judge=False`) and ZERO network calls (no `doi_verifier` unless
injected). It never raises from a public entry point — a garbage store or a
crashed rubric yields a degraded-but-valid certificate. Honesty is encoded as
schema, not tone: `not_checked` is a real status, every countable item reports
N-of-M, and coverage can only lower wording — never correctness (design §10.1).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Mandatory honesty strings (design §8.3) — the certificate must never overclaim.
_LIM_TURNITIN = ("This is NOT a Turnitin scan and cannot substitute for one.")
_LIM_CROSSREF = ("DOI existence is checked against CrossRef only; DataCite/arXiv DOIs can 404 "
                 "there. Metadata sanity is heuristic.")
_LIM_VALIDATED = ("`validated` numbers were supplied by the student (pasted, not computed by "
                  "DoThesis) and were checked for internal consistency only — DoThesis did not "
                  "compute them and cannot attest their origin.")
_LIM_UNSIGNED = ("This certificate is not cryptographically signed; `content_sha256` detects "
                 "accidental alteration only.")
_LIM_DEFENSE = ("Defense-drill completion is not yet recorded and is not attested.")
_LIM_PRUNED = ("The provenance ledger was truncated; early computations are not individually "
               "attested.")
_LIM_OFFLINE = ("Source verification ran offline; DOI existence was not re-checked.")

_STATUS = ("pass", "warn", "fail", "not_checked")


def _dim(rubric: dict, name: str) -> Optional[dict]:
    for d in (rubric.get("dimensions") or []):
        if isinstance(d, dict) and d.get("name") == name:
            return d
    return None


def _counts(dim: Optional[dict]) -> tuple:
    if not dim:
        return 0, 0
    fs = dim.get("findings") or []
    hard = sum(1 for f in fs if isinstance(f, dict) and f.get("severity") == "hard")
    soft = sum(1 for f in fs if isinstance(f, dict) and f.get("severity") == "soft")
    return hard, soft


def _evidence(dim: Optional[dict], name: str) -> List[dict]:
    if not dim:
        return []
    hard, soft = _counts(dim)
    ev = {"kind": "rubric_dim", "name": name, "findings_hard": hard, "findings_soft": soft}
    if isinstance(dim.get("meta"), dict):
        ev["meta"] = dim["meta"]
    return [ev]


def _item(iid, title, status, evidence, limitations=None, coverage=None) -> dict:
    d = {"id": iid, "title": title, "status": status, "evidence": evidence,
         "limitations": limitations or []}
    if coverage is not None:
        d["coverage"] = coverage
    return d


# --- the 11 checklist item builders (design §6.2 table) ---------------------

def _ck_rq_hypothesis_trace(cs, rubric) -> dict:
    hyps = ((cs.get("m3_design") or {}).get("hypotheses")) if isinstance(cs.get("m3_design"), dict) else None
    if hyps:
        status = "warn"  # existence only; semantic gap-trace is the judge's job
    else:
        status = "not_checked"
    return _item("rq_hypothesis_trace", "Research questions trace to hypotheses", status,
                 [{"kind": "state", "name": "m3_design.hypotheses",
                   "present": bool(hyps), "count": len(hyps) if hyps else 0}],
                 ["Deterministic check is existence + non-empty; semantic RQ→hypothesis "
                  "tracing is not attested in v1."])


def _ck_sources_verified(cs, rubric) -> dict:
    dim = _dim(rubric, "source_verification")
    meta = (dim or {}).get("meta") or {}
    checked, verified = meta.get("checked", 0), meta.get("verified", 0)
    total = len((cs.get("m2_literature") or {}).get("literature_sources") or []) if isinstance(
        cs.get("m2_literature"), dict) else 0
    hard, soft = _counts(dim)
    lims = [_LIM_CROSSREF]
    if total == 0:
        status = "not_checked"
    elif not meta.get("network_enabled", False):
        status = "warn"
        lims.append(_LIM_OFFLINE)
    elif hard == 0 and soft == 0 and verified == checked and checked > 0:
        status = "pass"
    else:
        status = "warn"
    return _item("sources_verified", "Every bibliography source is verification-passed", status,
                 _evidence(dim, "source_verification"), lims,
                 coverage={"checked": checked, "total": total})


def _ck_citation_integrity(cs, rubric) -> dict:
    dim = _dim(rubric, "citations")
    hard, soft = _counts(dim)
    status = "fail" if hard else ("warn" if soft else "pass")
    return _item("citation_integrity", "Every in-text citation has a matching reference", status,
                 _evidence(dim, "citations"))


def _ck_method_justified(cs, rubric, prov) -> dict:
    ops = (prov.get("ops_seen") or {}) if isinstance(prov, dict) else {}
    seen = "method_advice" in ops
    if seen:
        ma = ops.get("method_advice") or {}
        conflicts = ma.get("conflicts", 0) if isinstance(ma, dict) else 0
        status = "warn" if conflicts else "pass"
    else:
        status = "not_checked"
    return _item("method_justified", "The analysis method is defensible for the data + model",
                 status, [{"kind": "ledger", "name": "method_advice", "seen": seen}])


def _ck_power_defended(cs, rubric, prov) -> dict:
    ar = (cs.get("m4_analysis") or {}).get("analysis_results") if isinstance(
        cs.get("m4_analysis"), dict) else None
    has_power = isinstance(ar, dict) and (ar.get("power_analysis") or ar.get("sample_plan"))
    ops = (prov.get("ops_seen") or {}) if isinstance(prov, dict) else {}
    ledger_power = "power" in ops
    if has_power or ledger_power:
        status = "pass"
    else:
        status = "not_checked"
    return _item("power_defended", "Statistical power is defended", status,
                 [{"kind": "mixed", "power_block": bool(has_power), "ledger_power": bool(ledger_power)}])


def _ck_screening_documented(cs, rubric, prov) -> dict:
    ar = (cs.get("m4_analysis") or {}).get("analysis_results") if isinstance(
        cs.get("m4_analysis"), dict) else None
    ds = ar.get("data_screening") if isinstance(ar, dict) else None
    ops = (prov.get("ops_seen") or {}) if isinstance(prov, dict) else {}
    if ds or "screening" in ops:
        status = "pass"
    else:
        status = "not_checked"  # no dataset → normal, NOT a failure (design)
    return _item("screening_documented", "Data screening is documented", status,
                 [{"kind": "state", "data_screening": bool(ds)}],
                 ["No dataset present is reported as not_checked, not a failure."] if status == "not_checked" else [])


def _ck_measurement_model(cs, rubric) -> dict:
    dim = _dim(rubric, "stats_validity")
    hard, soft = _counts(dim)
    status = "fail" if hard else ("warn" if soft else "pass")
    return _item("measurement_model_reported", "The measurement model is reported and consistent",
                 status, _evidence(dim, "stats_validity"),
                 ["Surfaced validity breaches are creditable disclosure, not hidden flaws."] if soft else [])


def _ck_hypotheses_decided(cs, rubric) -> dict:
    dim = _dim(rubric, "coherence")  # coverage_findings ride the coherence dim
    ar = (cs.get("m4_analysis") or {}).get("analysis_results") if isinstance(
        cs.get("m4_analysis"), dict) else None
    tests = ar.get("hypothesis_tests") if isinstance(ar, dict) else None
    undecided = 0
    if isinstance(tests, list):
        undecided = sum(1 for t in tests if isinstance(t, dict) and not t.get("decision"))
    status = "fail" if undecided else ("pass" if tests else "not_checked")
    return _item("hypotheses_decided", "Every hypothesis has a decision from validated numbers",
                 status, [{"kind": "state", "undecided": undecided,
                           "total": len(tests) if isinstance(tests, list) else 0}])


def _ck_chapters_coherent(cs, rubric) -> dict:
    dim = _dim(rubric, "coherence")
    hard, soft = _counts(dim)
    status = "fail" if hard else ("warn" if soft else "pass")
    return _item("chapters_coherent", "Chapter prose agrees with the persisted numbers", status,
                 _evidence(dim, "coherence"))


def _ck_similarity_selfchecked(cs, rubric) -> dict:
    dim = _dim(rubric, "similarity")
    # similarity findings are ALWAYS soft — this item can never be `fail`.
    if dim is None:
        status = "not_checked"
    else:
        _, soft = _counts(dim)
        status = "warn" if soft else "pass"
    return _item("similarity_selfchecked", "Prose passed the internal similarity self-check",
                 status, _evidence(dim, "similarity"), [_LIM_TURNITIN])


def _ck_defense_drilled(cs, rubric) -> dict:
    return _item("defense_drilled", "The defense was rehearsed", "not_checked",
                 [{"kind": "none"}], [_LIM_DEFENSE])


def build_checklist(cs: dict, rubric: dict, prov: dict) -> List[dict]:
    """The 11 items in fixed order."""
    return [
        _ck_rq_hypothesis_trace(cs, rubric),
        _ck_sources_verified(cs, rubric),
        _ck_citation_integrity(cs, rubric),
        _ck_method_justified(cs, rubric, prov),
        _ck_power_defended(cs, rubric, prov),
        _ck_screening_documented(cs, rubric, prov),
        _ck_measurement_model(cs, rubric),
        _ck_hypotheses_decided(cs, rubric),
        _ck_chapters_coherent(cs, rubric),
        _ck_similarity_selfchecked(cs, rubric),
        _ck_defense_drilled(cs, rubric),
    ]


# --- assembly ---------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_provenance() -> dict:
    return {"numbers": {"total": 0, "computed": 0, "validated": 0, "unchecked": 0},
            "datasets": [], "ledger": {"pruned": False}, "ops_seen": {},
            "note": ("computed = calculated by DoThesis from the student's data file and matched "
                     "to a ledger row; validated = supplied by the student and checked for "
                     "internal consistency only; unchecked = free-text.")}


def _sha256_of(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_certificate(cs: Optional[dict], *, project_id: str = "", rubric: Optional[dict] = None,
                      doi_verifier=None, artifact_key: Optional[str] = None) -> dict:
    """Deterministic committee-readiness certificate. Never raises."""
    try:
        cs = cs if isinstance(cs, dict) else {}
        from quality.rubric import _detect_method, score_thesis  # noqa: PLC0415
        judge_included = False
        if rubric is None:
            rubric = score_thesis(cs, include_judge=False, doi_verifier=doi_verifier)
        else:
            judge_included = any(
                isinstance(d, dict) and d.get("name") in ("methodology", "writing")
                for d in (rubric.get("dimensions") or []))
        method = rubric.get("method") or _detect_method(cs)

        prov = None
        m4 = cs.get("m4_analysis")
        if isinstance(m4, dict) and isinstance(m4.get("analysis_provenance"), dict):
            prov = m4["analysis_provenance"]
        prov = prov or _empty_provenance()

        checklist = build_checklist(cs, rubric, prov)
        blocking = list(rubric.get("blocking") or [])
        any_fail = any(it["status"] == "fail" for it in checklist)
        status = "ready" if (not blocking and not any_fail) else "not_ready"

        # advisory (never feeds readiness)
        try:
            from quality.similarity import similarity_report  # noqa: PLC0415
            sim = similarity_report(cs)
        except Exception:
            sim = {"headline": None, "coverage_note": "similarity report unavailable"}
        judge_dims = None
        if judge_included:
            judge_dims = [d for d in rubric["dimensions"]
                          if isinstance(d, dict) and d.get("name") in ("methodology", "writing")]
        adv = rubric.get("advisor") or {}
        advisory = {"similarity": sim, "judge_dimensions": judge_dims,
                    "advisor_directives": {"total": adv.get("total", 0),
                                           "addressed": adv.get("addressed", 0),
                                           "open": adv.get("open", 0)}}

        # limitations — mandatory strings + rider ones
        network_enabled = bool(((_dim(rubric, "source_verification") or {}).get("meta") or {})
                               .get("network_enabled", False))
        limitations = [_LIM_VALIDATED, _LIM_UNSIGNED, _LIM_DEFENSE, _LIM_CROSSREF]
        cov_note = sim.get("coverage_note")
        if cov_note:
            limitations.append(cov_note)
        if (prov.get("ledger") or {}).get("pruned"):
            limitations.append(_LIM_PRUNED)
        if not network_enabled:
            limitations.append(_LIM_OFFLINE)

        title = ((cs.get("m1_topic") or {}).get("research_title")
                 if isinstance(cs.get("m1_topic"), dict) else None)
        engine_ver = _engine_version()
        cert = {
            "schema_version": SCHEMA_VERSION, "kind": "dothesis.certificate",
            "generated_at": _now_iso(), "project_id": project_id,
            "thesis": {"title": title, "method": method},
            "engine": {"thesis_stats": engine_ver, "rubric": "deterministic",
                       "judge_included": judge_included},
            "readiness": {"status": status, "overall_score": round(float(rubric.get("overall", 0.0)), 4),
                          "blocking": blocking},
            "checklist": checklist, "provenance": prov, "advisory": advisory,
            "limitations": limitations,
            "attestation": _attestation(status, checklist, prov, network_enabled),
        }
        if artifact_key:
            cert["artifact"] = artifact_key
        # tamper-evidence: hash over the cert minus the volatile/self fields
        digest_src = {k: v for k, v in cert.items() if k not in ("content_sha256", "generated_at")}
        cert["content_sha256"] = _sha256_of(digest_src)
        return cert
    except Exception:
        logger.exception("build_certificate failed; returning degraded certificate")
        return _degraded(project_id)


def _degraded(project_id: str) -> dict:
    cert = {"schema_version": SCHEMA_VERSION, "kind": "dothesis.certificate",
            "generated_at": _now_iso(), "project_id": project_id,
            "thesis": {"title": None, "method": "unknown"},
            "engine": {"thesis_stats": _engine_version(), "rubric": "deterministic",
                       "judge_included": False},
            "readiness": {"status": "not_ready", "overall_score": 0.0, "blocking": []},
            "checklist": [], "provenance": _empty_provenance(),
            "advisory": {"similarity": None, "judge_dimensions": None,
                         "advisor_directives": {"total": 0, "addressed": 0, "open": 0}},
            "limitations": ["The certificate could not be fully assembled from the project state; "
                            "treat this as not ready.", _LIM_UNSIGNED],
            "attestation": "DoThesis could not assemble a full readiness certificate for this "
                           "project; no readiness is asserted."}
    digest_src = {k: v for k, v in cert.items() if k not in ("content_sha256", "generated_at")}
    cert["content_sha256"] = _sha256_of(digest_src)
    return cert


def _engine_version() -> str:
    try:
        import thesis_stats  # noqa: PLC0415
        return thesis_stats.__version__
    except Exception:
        return "unknown"


def _attestation(status, checklist, prov, network_enabled) -> str:
    passed = sum(1 for it in checklist if it["status"] == "pass")
    nums = prov.get("numbers") or {}
    gate = prov.get("gate") or {}
    # "all gates ran" vs "no gate failed" (gap 2): only assertable when the gate
    # record confirms the verifier actually executed.
    if gate.get("stats_validation") == "ran":
        gate_clause = " The statistics-verification gate ran on the committed numbers."
    elif gate.get("stats_validation") == "unavailable":
        gate_clause = " Note: the statistics-verification gate did not run for this commit."
    else:
        gate_clause = ""
    return (f"DoThesis ran {len(checklist)} deterministic committee-readiness checks; "
            f"{passed} passed. Of {nums.get('total', 0)} reported numbers, "
            f"{nums.get('computed', 0)} were computed by DoThesis and matched to a provenance "
            f"ledger, {nums.get('validated', 0)} were student-supplied and checked only for "
            f"internal consistency.{gate_clause} DoThesis did not run a plagiarism scan, did not "
            f"verify DOIs {'online' if network_enabled else 'at all (offline)'}, and does not attest "
            f"a defense rehearsal. Readiness: {status}.")


# --- gate_summary (B2B, <2 KB) ----------------------------------------------

def gate_summary(cert: dict) -> dict:
    checklist = cert.get("checklist") or []
    items = [{"id": it["id"], "status": it["status"], "blocking": it["status"] == "fail"}
             for it in checklist]
    prov_nums = (cert.get("provenance") or {}).get("numbers") or {}
    sv = next((it for it in checklist if it["id"] == "sources_verified"), {})
    sv_cov = sv.get("coverage") or {}
    return {"schema_version": SCHEMA_VERSION, "project_id": cert.get("project_id", ""),
            "generated_at": cert.get("generated_at"),
            "ready": (cert.get("readiness") or {}).get("status") == "ready",
            "deterministic": True, "items": items,
            "blocking": list((cert.get("readiness") or {}).get("blocking") or [])[:20],
            "coverage": {"numbers": {k: prov_nums.get(k, 0)
                                     for k in ("computed", "validated", "unchecked", "total")},
                         "sources": {"verified": sv_cov.get("checked", 0),
                                     "checked": sv_cov.get("checked", 0),
                                     "total": sv_cov.get("total", 0)}},
            "certificate": {"content_sha256": cert.get("content_sha256"),
                            "artifact": cert.get("artifact")}}


# --- markdown render (export appendix) --------------------------------------

_STATUS_LABEL = {"pass": "✅ pass", "warn": "⚠️ warn", "fail": "❌ fail",
                 "not_checked": "◻️ not checked"}


def render_certificate_md(cert: dict) -> str:
    """Deterministic markdown appendix. Leads with verified content so a
    low-coverage certificate reads as truthful, not as a failure grade."""
    r = cert.get("readiness") or {}
    lines = ["# DoThesis Verification Report", "",
             f"**Readiness:** {r.get('status', 'unknown')}  ·  "
             f"**Overall score:** {r.get('overall_score', 0)}", ""]
    checklist = cert.get("checklist") or []
    order = {"pass": 0, "warn": 1, "fail": 2, "not_checked": 3}
    ordered = sorted(checklist, key=lambda it: order.get(it["status"], 4))
    lines += ["## Checklist", "", "| Check | Status | Coverage |", "|---|---|---|"]
    for it in ordered:
        cov = it.get("coverage")
        cov_s = f"{cov['checked']} of {cov['total']}" if cov else "—"
        lines.append(f"| {it['title']} | {_STATUS_LABEL.get(it['status'], it['status'])} | {cov_s} |")
    nums = (cert.get("provenance") or {}).get("numbers") or {}
    lines += ["", "## Number provenance", "",
              f"{nums.get('computed', 0)} of {nums.get('total', 0)} reported numbers were computed "
              f"by DoThesis and matched to a provenance ledger; {nums.get('validated', 0)} were "
              f"student-supplied and checked for internal consistency only.", "",
              "## What this certificate does not claim", ""]
    for lim in (cert.get("limitations") or []):
        lines.append(f"- {lim}")
    lines += ["", "---", "", cert.get("attestation", ""), "",
              f"`content_sha256: {cert.get('content_sha256', '')[:16]}…`"]
    return "\n".join(lines)
