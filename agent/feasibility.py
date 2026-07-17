"""M1 topic feasibility — early sample-size reality check + operationalizability.

Pure, deterministic, ADVISORY, never-raises (the voice of agent/preflight.py and
agent/coherence.py). Front-loads at M1 the two questions that sink a quantitative
thesis late: "can you actually sample the N this model needs?" and "is this RQ a
testable relationship or just a describable topic?" — powered by the SAME shipped
power engine M3/M4 use, so the M1 forecast and the M3 computed plan agree by
construction (same `medium` effect-size convention; only the predictor count k
differs pre-model).

Nothing here blocks anything: feasibility is advice, surfaced once, warmly.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Relationship markers (EN + VI) — the shared lexicon for k-inference AND the
# operationalizability check (a testable RQ asserts a relationship).
_REL_MARKERS = [
    r"affect", r"influenc", r"impact", r"effect", r"relationship", r"relate",
    r"predict", r"determin", r"driv", r"lead to", r"associat", r"correlat",
    r"depend", r"moderat", r"mediat", r"contribut",
    r"ảnh hưởng", r"tác động", r"mối quan hệ", r"quan hệ", r"dự đoán",
    r"ảnh hưởng đến", r"tác động đến", r"quyết định",
]
_REL_RE = re.compile("|".join(_REL_MARKERS))
_DEFINITIONAL_RE = re.compile(r"what is|what are|meaning of|the concept of|define\b|definition of|là gì|khái niệm")
_NORMATIVE_RE = re.compile(r"\bshould\b|\bought\b|\bmust\b|is it (right|ethical|good)|có nên|nên\b")

_QUAL = ("qualitative", "định tính")


def _fold(text: Any) -> str:
    return unicodedata.normalize("NFC", str(text or "")).casefold()


def _has_relationship_marker(text: Any) -> bool:
    return bool(_REL_RE.search(_fold(text)))


# --- sample-size estimate ---------------------------------------------------

def _infer_k(m1: dict, expected_constructs: int, rqs: List[str]) -> tuple:
    """k ladder (D2): explicit constructs-1 → #relationship-RQs → default 4."""
    if isinstance(expected_constructs, int) and expected_constructs > 0:
        return max(1, min(12, expected_constructs - 1)), "student_stated"
    rel = sum(1 for q in rqs if _has_relationship_marker(q))
    if rel:
        return max(1, min(12, max(2, min(8, rel)))), "inferred_from_rqs"
    return 4, "default"


def _power_estimate(analysis: str, k: int) -> Optional[dict]:
    """One family's a-priori N via the shipped engine. None on any failure."""
    try:
        import thesis_stats as ts  # noqa: PLC0415 (lazy: module imports without the submodule)
        r = ts.run_power(analysis, "apriori", effect_size="medium", predictors=k)
        n = r.get("recommended_n") or r.get("required_n")
        if not isinstance(n, (int, float)):
            return None
        return {"analysis": analysis, "required_n": int(n),
                "justification": r.get("justification") or ""}
    except Exception:
        logger.debug("feasibility: power estimate failed for %s k=%s", analysis, k, exc_info=True)
        return None


def _heuristic_estimate(analysis: str, k: int) -> dict:
    from agent.sampling import target_sample_n  # noqa: PLC0415
    method = {"pls_sem": "pls", "cb_sem": "cb-sem", "regression": "regression"}.get(analysis, "regression")
    n, rule = target_sample_n(method, n_paths=k, n_indicators=0)
    return {"analysis": analysis, "required_n": int(n), "justification": rule}


def _population(m1: dict) -> str:
    pop = (m1.get("target_population") or m1.get("scope") or "").strip() if isinstance(m1, dict) else ""
    return pop or "your intended population"


def estimate_sample_size(m1: Optional[dict], expected_constructs: int = 0,
                         method_hint: str = "") -> dict:
    """Early required-N forecast. Never raises. status ∈ estimate|range|skipped."""
    try:
        m1 = m1 if isinstance(m1, dict) else {}
        rqs = [q for q in (m1.get("research_questions") or []) if isinstance(q, str)]
        rtype = _fold(m1.get("research_type"))
        pop = _population(m1)
        if any(q in rtype for q in _QUAL):
            return {"status": "skipped", "basis": "none", "estimates": [], "headline_n": None,
                    "assumed": {}, "skipped_reason": "Research type is qualitative — a survey "
                    "sample-size power analysis does not apply.",
                    "message": "Feasibility sample-size estimate skipped for a qualitative design."}

        from agent.method_advisor import normalize_method  # noqa: PLC0415
        fam = normalize_method(method_hint)
        k, ksrc = _infer_k(m1, expected_constructs, rqs)

        # CB-SEM has no power op → the Kline heuristic floor.
        if fam == "cb_sem":
            est = _heuristic_estimate("cb_sem", k)
            return _assemble("estimate", "heuristic", [est], k, ksrc, pop)

        # Choose the family set: a mapped hint → that one family; else both.
        families = [fam] if fam in ("pls_sem", "regression", "nonparametric") else ["pls_sem", "regression"]
        families = ["regression" if f == "nonparametric" else f for f in families]

        basis = "power"
        estimates: List[dict] = []
        for f in families:
            e = _power_estimate(f, k)
            if e is None:
                e = _heuristic_estimate(f, k)
                basis = "heuristic"
            estimates.append(e)
        if not estimates:  # canonical last-ditch shape (cannot happen, but keep the invariant)
            return {"status": "range", "basis": "heuristic",
                    "estimates": [{"analysis": "regression", "required_n": 100, "justification": ""},
                                  {"analysis": "pls_sem", "required_n": 200, "justification": ""}],
                    "headline_n": 200, "range": [100, 200],
                    "assumed": {"predictors": k, "predictors_source": ksrc},
                    "message": _message(200, [100, 200], pop)}
        status = "estimate" if len(estimates) == 1 else "range"
        return _assemble(status, basis, estimates, k, ksrc, pop)
    except Exception:
        logger.exception("estimate_sample_size failed (fail-open)")
        return {"status": "range", "basis": "heuristic",
                "estimates": [{"analysis": "regression", "required_n": 100, "justification": ""},
                              {"analysis": "pls_sem", "required_n": 200, "justification": ""}],
                "headline_n": 200, "range": [100, 200], "assumed": {"predictors": 4,
                "predictors_source": "default"}, "message": _message(200, [100, 200],
                "your intended population")}


def _assemble(status, basis, estimates, k, ksrc, pop) -> dict:
    ns = [e["required_n"] for e in estimates]
    headline = max(ns)
    out = {"status": status, "basis": basis, "estimates": estimates, "headline_n": headline,
           "assumed": {"predictors": k, "predictors_source": ksrc}}
    if status == "range":
        out["range"] = [min(ns), max(ns)]
        out["message"] = _message(headline, out["range"], pop)
    else:
        out["message"] = _message(headline, None, pop)
    return out


def _message(headline, rng, pop) -> str:
    span = f"n ≈ {rng[0]}–{rng[1]}" if rng else f"n ≈ {headline}"
    return (f"A model like this typically needs {span}. Can you realistically sample "
            f"that many from {pop}? M3 will compute the exact figure from your actual model.")


# --- operationalizability ---------------------------------------------------

def check_operationalizability(rqs: Any, research_type: Optional[str] = None) -> dict:
    """Flag RQs that can't be operationalized as a measurable relationship.
    Advisory, never raises. Accepts a str or a list."""
    try:
        if isinstance(rqs, str):
            items = [rqs]
        elif isinstance(rqs, list):
            items = [q for q in rqs if isinstance(q, str) and q.strip()]
        else:
            items = []
        rtype = _fold(research_type)
        findings: List[dict] = []
        testable = 0
        any_relationship = False
        for q in items:
            f = _fold(q)
            if _DEFINITIONAL_RE.search(f):
                findings.append({"rq": q, "kind": "definitional", "severity": "advisory",
                                 "reframe_hint": "Reframe as a relationship, e.g. 'How does X affect Y?' "
                                 "— a definition is not a testable hypothesis."})
            elif _NORMATIVE_RE.search(f):
                findings.append({"rq": q, "kind": "normative", "severity": "advisory",
                                 "reframe_hint": "Turn the value judgment into a measurable question, "
                                 "e.g. 'What is the effect of X on Y?' — a survey tests what IS, not what OUGHT."})
            elif _has_relationship_marker(q):
                any_relationship = True
                testable += 1
            else:
                findings.append({"rq": q, "kind": "no_measurable_relationship", "severity": "advisory",
                                 "reframe_hint": "State the constructs and the relationship you expect "
                                 "between them so it can be measured and tested."})
        # Topic-level: an explicitly quantitative design with nothing testable.
        if items and not any_relationship and ("quantitative" in rtype or "định lượng" in rtype):
            findings.append({"rq": None, "kind": "topic_not_testable", "severity": "advisory",
                             "reframe_hint": "None of your research questions asserts a measurable "
                             "relationship — a quantitative thesis needs at least one testable hypothesis."})
        return {"findings": findings, "testable_count": testable, "total": len(items)}
    except Exception:
        logger.exception("check_operationalizability failed (fail-open)")
        return {"findings": [], "testable_count": 0, "total": 0}


# --- store-bound tool -------------------------------------------------------

def make_feasibility_tool(store) -> list:
    """Build the M1 feasibility tool bound to one project's state store."""
    from langchain_core.tools import tool  # noqa: PLC0415
    import json  # noqa: PLC0415

    @tool
    def topic_feasibility(expected_constructs: int = 0, method_hint: str = "") -> str:
        """Early feasibility reality check for THIS topic: the sample size a model
        like this typically needs (so the student knows before committing whether
        they can sample it), plus a soft flag on any research question that isn't a
        testable relationship. Advisory — run ONCE before locking the topic; never
        blocks. Pass expected_constructs / method_hint only if the student stated them.
        Read-only-advice over thesis state (persists the estimate for later reuse)."""
        cs = (store.load() or {}).get("contextStore") or {}
        m1 = {k: cs.get(k) for k in ("research_title", "research_questions",
                                     "research_type", "target_population", "scope")}
        payload = {"advisory": True,
                   "sample_size": estimate_sample_size(m1, expected_constructs, method_hint),
                   "operationalizability": check_operationalizability(
                       m1.get("research_questions"), m1.get("research_type"))}
        payload["inputs"] = {"predictors_source": payload["sample_size"]["assumed"].get("predictors_source")}
        try:
            store.commit_slice("M1", {"feasibility": payload},
                               reason="topic_feasibility: early sample-size reality check")
        except Exception:
            logger.exception("topic_feasibility: persist failed (advisory, non-fatal)")
        return json.dumps(payload, ensure_ascii=False)

    return [topic_feasibility]
