"""Rubric scorer: deterministic dimensions (reusing existing validators) + bounded
LLM-judge dimensions -> a RubricResult. Read-only over a nested context_store, so it
can never corrupt a thesis. institution_profile + advisor_feedback are read with safe
defaults (owned by the cross-session-memory spec)."""
from __future__ import annotations

import json as _json
import logging

logger = logging.getLogger(__name__)

_ALL_CHAPTERS = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def _sections(context_store: dict) -> list[dict]:
    # Decision: tolerate both v3 (final_sections list) and auto-mode (chapters
    # dict) shapes so the rubric works regardless of how the draft was produced.
    m5 = context_store.get("m5_writing") or {}
    return m5.get("final_sections") or list((m5.get("chapters") or {}).values()) or []


def _all_prose(context_store: dict) -> str:
    return "\n\n".join((s.get("prose") or "") for s in _sections(context_store))


def deterministic_dimensions(context_store: dict) -> list[dict]:
    # Decision: import the engine validators lazily so the quality package stays
    # import-light and there's no layering cost just to `import quality.rubric`.
    from orchestrator.tools.m5_writing import (  # noqa: PLC0415
        assess_export_readiness, validate_citations_plain, _is_stub_prose,
    )

    # 1) Structure — reuse the single completeness gate (Spec 1). Full/unscoped is
    #    correct for a whole-thesis review (F0: back-compat, 1-arg call).
    missing = assess_export_readiness(context_store)
    structure = {
        "name": "structure", "weight": 0.20,
        "score": max(0.0, 1.0 - 0.2 * len(missing)),
        "findings": [{"issue": m, "fix": f"Provide {m}.", "chapter": "-", "severity": "hard"}
                     for m in missing],
    }

    # 2) Citation integrity — an uncited (Author, Year) is a source not in the
    #    reference pool (a likely fabrication). Reuse the autosave validator.
    pool = (context_store.get("m2_literature") or {}).get("literature_sources") or []
    cite = validate_citations_plain(_all_prose(context_store), pool)
    uncited = cite["uncited_warnings"]
    # F5 (F0 decision): emit the hallucination-catch signal HERE — this is F3's
    # citation dimension, the single place uncited (likely-fabricated) citations
    # are detected. quality already imports agent (preflight/instrument dims), so
    # agent.analytics.emit adds no new layering edge; it's a no-op until the app
    # wires it. One event per rejected citation, breakdown-able by `kind`.
    if uncited:
        from agent.analytics import emit  # noqa: PLC0415
        for u in uncited:
            emit("citation_rejected", None, {"kind": "uncited", "citation": str(u)})
    citations = {
        "name": "citations", "weight": 0.20,
        "score": 1.0 if not uncited else max(0.0, 1.0 - 0.1 * len(uncited)),
        "findings": [{"issue": f"Citation {u} has no matching reference (possible fabrication).",
                      "fix": "Add the source to your references or remove the citation.",
                      "chapter": "-", "severity": "hard"} for u in uncited],
    }

    # 3) Stub prose — placeholder/failure text masquerading as a chapter.
    stub_findings = [
        {"issue": f"Section '{s.get('title')}' is a stub/placeholder, not real content.",
         "fix": "Compose or rewrite this section with real content.",
         "chapter": s.get("title", "-"), "severity": "hard"}
        for s in _sections(context_store) if _is_stub_prose(s.get("prose") or "")
    ]
    stubs = {"name": "no_stubs", "weight": 0.10,
             "score": 1.0 if not stub_findings else 0.0, "findings": stub_findings}

    return [structure, citations, stubs]


METHOD_CRITERIA: dict[str, list[str]] = {
    "pls-sem": ["cronbach", "composite reliability|cr", "ave", "htmt",
                "path coefficient|β|beta", "r2|r-square|r²", "p value|p-value|p<"],
    "cb-sem":  ["cronbach", "cfa|factor loading", "cfi", "rmsea", "tli|nfi",
                "chi-square|χ2", "path coefficient|β"],
    "spss":    ["cronbach", "kmo|bartlett", "regression|beta|β", "r2|r-square",
                "vif|tolerance", "f statistic|f=", "p value|p<"],
    "generic": ["reliability", "validity", "coefficient", "p value|p<"],
}


def results_validity_dimension(context_store: dict, method: str) -> dict:
    # Decision: deterministic presence check of the method's required statistics
    # in the analysis_results text — cheap, method-aware, no LLM. Findings are
    # SOFT (advisory): the hard data gate stays M4's job, not ours.
    import re  # noqa: PLC0415
    raw = (context_store.get("m4_analysis") or {}).get("analysis_results") or ""
    # analysis_results is a structured dict in the current M4 schema (and can be a
    # legacy string); serialize non-strings so the presence regex still matches.
    text = (raw if isinstance(raw, str) else _json.dumps(raw, default=str)).lower()
    crits = METHOD_CRITERIA.get(method, METHOD_CRITERIA["generic"])
    findings = []
    for pattern in crits:
        if not re.search(pattern, text):
            label = pattern.split("|")[0]
            findings.append({"issue": f"Results don't report {label} (expected for {method}).",
                             "fix": f"Report and interpret {label} in your Results chapter.",
                             "chapter": "results", "severity": "soft"})
    score = 1.0 - (len(findings) / max(1, len(crits)))
    return {"name": "results_validity", "weight": 0.20, "score": round(score, 3),
            "findings": findings}


def preflight_dimension(context_store: dict) -> dict:
    """Methods pre-flight as a soft rubric dimension (F8 Task 3).

    Decision: reuse the SAME pure check the agent's methods_preflight tool runs
    (agent.preflight.preflight_check) so the rubric and the live coaching surface
    can never disagree about what 'analysis-ready' means. Import is lazy + local
    to keep quality import-light and avoid any agent<->quality load cycle
    (agent.preflight is pure; quality.rubric only reaches into it here). Findings
    are SOFT — a design gap is advisory, not a hard blocker on the thesis."""
    from agent.preflight import preflight_check  # noqa: PLC0415
    missing = preflight_check(context_store)
    # Each missing item shaves 0.15 (plan-specified) so a couple of gaps still
    # leaves a usable-but-flagged score; floored at 0 so it never goes negative.
    score = max(0.0, 1.0 - 0.15 * len(missing))
    findings = [{"issue": m, "fix": "Address this before running M4 analysis.",
                 "chapter": "methodology", "severity": "soft"} for m in missing]
    return {"name": "preflight", "weight": 0.10, "score": round(score, 3),
            "findings": findings}


def instrument_quality_dimension(context_store: dict) -> dict:
    """Questionnaire Doctor as a soft rubric dimension (F7 Task 1).

    Decision: reuse the SAME pure lint the agent's audit_instrument tool runs
    (agent.tools.instrument.audit_instrument_findings) so the rubric and the live
    coaching surface can never disagree about instrument quality. Lazy + local
    import keeps quality import-light and mirrors preflight_dimension's approach.

    Constructs are derived from the instrument's own item.construct fields (the
    rubric has no separate construct list), so a construct with no reverse-coded
    item still gets flagged. Findings are SOFT — an item-wording gap is advisory,
    never a hard block on the thesis."""
    from agent.tools.instrument import audit_instrument_findings  # noqa: PLC0415
    m3 = context_store.get("m3_design") or {}
    instrument = m3.get("instrument") or {}
    hypotheses = m3.get("hypotheses") or []
    items = instrument.get("items") or []
    # Ordered-unique construct names present on the items.
    constructs = list(dict.fromkeys(i.get("construct") for i in items if i.get("construct")))
    sources = (context_store.get("m2_literature") or {}).get("literature_sources") or []
    language = (context_store.get("m1_topic") or {}).get("language") or "en"
    findings = audit_instrument_findings(instrument, hypotheses, constructs,
                                         sources=sources, language=language)["findings"]
    # Each flagged item/coverage gap shaves 0.1, floored at 0 — a couple of soft
    # issues still leaves a usable score.
    score = max(0.0, 1.0 - 0.1 * len(findings))
    return {"name": "instrument_quality", "weight": 0.10, "score": round(score, 3),
            "findings": findings}


def apply_institution_overlay(dims: list[dict], profile: dict | None,
                              context_store: dict) -> list[dict]:
    """Override dimension weights and add hard requirement findings. Pure over dims.

    Decision: institution_profile is read with an EMPTY DEFAULT (F3 decouples
    from F4) — no profile means a generic rubric, never a crash."""
    if not profile:
        return dims
    out = [dict(d) for d in dims]
    for d in out:
        w = (profile.get("weight_overrides") or {}).get(d["name"])
        if w is not None:
            d["weight"] = w

    min_refs = profile.get("min_references")
    if min_refs:
        n = len((context_store.get("m2_literature") or {}).get("literature_sources") or [])
        if n < min_refs:
            for d in out:
                if d["name"] == "citations":
                    d["findings"] = d["findings"] + [{
                        "issue": f"Only {n} references; your institution requires >= {min_refs}.",
                        "fix": f"Add at least {min_refs - n} more sources.",
                        "chapter": "lit_review", "severity": "hard"}]
                    d["score"] = min(d["score"], 0.5)
    return out


def judge_dimension(name: str, weight: float, prompt: str, context_store: dict) -> dict:
    """One bounded LLM-judge call. Best-effort: any failure => neutral score + note,
    so the overall score always returns (Global Constraint: never crash)."""
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        # Decision (deviation from plan literal): if there's no JSON object at
        # all, RAISE into the except branch so we emit a "could not evaluate"
        # finding rather than silently returning a neutral score with no note —
        # that's what the bad-json robustness test proves.
        if s == -1 or e == -1:
            raise ValueError("no JSON object in judge response")
        data = _json.loads(content[s:e + 1])
        score = float(data.get("score", 0.6))
        findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
        return {"name": name, "weight": weight, "score": max(0.0, min(1.0, score)),
                "findings": findings}
    except Exception:
        logger.exception("quality: judge '%s' failed", name)
        return {"name": name, "weight": weight, "score": 0.6,
                "findings": [{"issue": f"Could not evaluate {name} automatically.",
                              "fix": "Review this dimension manually.", "chapter": "-",
                              "severity": "soft"}]}


def _judge_prompt(name: str, context_store: dict) -> str:
    m1 = context_store.get("m1_topic") or {}
    m3 = context_store.get("m3_design") or {}
    body = _all_prose(context_store)[:8000]
    rubric = {
        "methodology": "Do the hypotheses trace to stated research gaps, and does the chosen "
                       "method match the research design? Score 0..1.",
        "writing": "Is the prose coherent, academic in tone, and free of placeholder stubs? "
                   "Score 0..1.",
    }[name]
    return (f"You are a thesis examiner. {rubric}\nReturn STRICT JSON: "
            '{"score": <0..1>, "findings": [{"issue","fix","chapter","severity"}]}\n\n'
            f"Title: {m1.get('research_title')}\nHypotheses: {m3.get('hypotheses')}\n"
            f"Gaps: {(context_store.get('m2_literature') or {}).get('research_gaps')}\n\n"
            f"DRAFT:\n{body}")


def advisor_dimension(advisor_feedback: list[dict]) -> tuple[dict, dict]:
    """Turn open professor directives into hard findings + a N-of-M summary.

    Decision: advisor_feedback is read with an EMPTY DEFAULT ([]) — F3 does not
    hard-depend on F4; with no feedback the dimension is a perfect 1.0 no-op."""
    fb = advisor_feedback or []
    open_items = [f for f in fb if f.get("status") == "open"]
    summary = {"total": len(fb), "addressed": sum(1 for f in fb if f.get("status") == "addressed"),
               "open": open_items}
    findings = [{"issue": f"Advisor required (not yet addressed): {o.get('issue')}",
                 "fix": o.get("required_change", "Address this advisor comment."),
                 "chapter": o.get("chapter", "-"), "severity": "hard"} for o in open_items]
    score = 1.0 if not fb else summary["addressed"] / len(fb)
    return {"name": "advisor", "weight": 0.20, "score": round(score, 3),
            "findings": findings}, summary


def _weighted(dims: list[dict]) -> float:
    # Weights are illustrative and don't sum to 1; normalize by total weight so
    # institution overlays that change weights don't skew the 0..1 overall.
    total_w = sum(d["weight"] for d in dims) or 1.0
    return round(sum(d["score"] * d["weight"] for d in dims) / total_w, 3)


def stats_validity_dimension(context_store: dict) -> dict:
    """Deterministic correctness of the reported statistics (F#1 self-validation).

    Distinct from results_validity (which only presence-checks that a metric is
    mentioned): this reruns the thesis-stats verification arithmetic over the
    persisted results and turns HARD findings (impossible / self-contradictory
    numbers) into blocking rubric findings — the safety net for results that
    entered state without passing the chat commit gate (orchestrator path,
    legacy projects, direct writes). Lazy import + never crashes; free text
    scores ~1.0 with a soft 'unstructured' note. Weight 0.15."""
    m4 = context_store.get("m4_analysis") or {}
    block = m4.get("analysis_results")
    if block is None and isinstance(m4.get("results"), dict):
        block = m4  # orchestrator {results: {step: StepResult}} shape
    findings: list[dict] = []
    if block is not None:
        try:
            from agent.stats_validation import validate_analysis_results  # noqa: PLC0415
            agg = validate_analysis_results(block)
            for f in agg["findings"]:
                findings.append({
                    "issue": f["message"],
                    "fix": ("Re-run the analysis or correct the pasted/typed values so this "
                            "number is possible and internally consistent."),
                    "chapter": "results", "severity": f["severity"]})
        except Exception:
            logger.exception("stats_validity_dimension failed (fail-open)")
    hard = sum(1 for f in findings if f["severity"] == "hard")
    soft = sum(1 for f in findings if f["severity"] == "soft")
    score = max(0.0, 1.0 - 0.5 * hard - 0.1 * soft)
    return {"name": "stats_validity", "weight": 0.15, "score": round(score, 3),
            "findings": findings}


# --- Source (DOI) verification (roadmap #5) ---------------------------------
# Offline by default: Layer A (DOI syntax + engine author/metadata junk checks)
# is pure; Layer B (CrossRef DOI existence) runs ONLY when a verifier is injected
# or DOTHESIS_RUBRIC_DOI_CHECK=1. All findings SOFT — a 404 at CrossRef is strong
# evidence, not proof (DataCite/arXiv DOIs 404 there), so nothing enters `blocking`.
_DOI_CACHE: dict = {}  # normalized_doi -> (verdict: bool|None, ts: float)
_DOI_TTL_OK, _DOI_TTL_NONE = 24 * 3600, 300
_DOI_MAX_LOOKUPS, _DOI_TIME_BUDGET = 20, 10.0


def _normalize_doi(doi) -> str:
    if not isinstance(doi, str):
        return ""
    d = doi.strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip()


def _doi_syntax_ok(doi: str) -> bool:
    import re  # noqa: PLC0415
    return bool(re.match(r"^10\.\d{4,9}/\S+$", doi, re.I))


def _default_doi_verifier():
    """Real CrossRef verifier with a module-level cache + budget. Lazy engine
    import; returns None (never raises) on any failure. Only built when enabled."""
    import time  # noqa: PLC0415
    try:
        from engine.utils.citation_validator import CitationValidator  # noqa: PLC0415
    except Exception:
        return None
    validator = CitationValidator(timeout=3)

    def verify(doi: str):
        now = time.time()
        hit = _DOI_CACHE.get(doi)
        if hit is not None:
            verdict, ts = hit
            if now - ts < (_DOI_TTL_OK if verdict is not None else _DOI_TTL_NONE):
                return verdict
        try:
            verdict = validator.validate_doi(doi)
        except Exception:
            verdict = None
        _DOI_CACHE[doi] = (verdict, now)
        return verdict

    return verify


def _sv_finding(issue: str, fix: str = "Verify the source against its original record.") -> dict:
    return {"issue": issue, "fix": fix, "chapter": "lit_review", "severity": "soft"}


def source_verification_dimension(context_store: dict, doi_verifier=None) -> dict:
    """Author/metadata sanity + (opt-in) CrossRef DOI existence over the M2
    literature pool. Advisory (all soft), fail-open, offline unless a verifier is
    injected or DOTHESIS_RUBRIC_DOI_CHECK=1. Weight 0.10."""
    import os
    import time
    sources = (context_store.get("m2_literature") or {}).get("literature_sources") or []
    findings: list[dict] = []
    meta = {"checked": 0, "verified": 0, "unverified": 0, "no_doi": 0, "network_enabled": False}
    events: list[tuple] = []

    verifier = doi_verifier
    if verifier is None and os.getenv("DOTHESIS_RUBRIC_DOI_CHECK") == "1":
        verifier = _default_doi_verifier()
    meta["network_enabled"] = verifier is not None

    validator = None
    try:
        from engine.utils.citation_validator import CitationValidator  # noqa: PLC0415
        validator = CitationValidator(timeout=3)
    except Exception:
        logger.debug("source_verification: engine validator unavailable", exc_info=True)

    start, lookups = time.time(), 0
    for src in sources:
        if not isinstance(src, dict):
            continue
        if validator is not None:
            try:
                authors = src.get("authors")
                alist = authors if isinstance(authors, list) else ([authors] if authors else [])
                for msg in validator.check_author_sanity(alist):
                    findings.append(_sv_finding(f"Author issue: {msg}"))
                    events.append(("author_sanity", msg))
                for msg in validator.check_metadata_quality(src):
                    findings.append(_sv_finding(f"Citation metadata: {msg}"))
                    events.append(("junk_metadata", msg))
            except Exception:
                logger.debug("source_verification: junk check failed", exc_info=True)

        norm = _normalize_doi(src.get("doi"))
        if not norm:
            meta["no_doi"] += 1
            continue
        if not _doi_syntax_ok(norm):
            findings.append(_sv_finding(f"Malformed DOI '{src.get('doi')}'.",
                                        "Fix the DOI or remove it."))
            events.append(("malformed_doi", src.get("doi")))
            continue
        if verifier is None:
            continue
        if lookups >= _DOI_MAX_LOOKUPS or (time.time() - start) > _DOI_TIME_BUDGET:
            meta["unverified"] += 1
            continue
        lookups += 1
        meta["checked"] += 1
        try:
            verdict = verifier(norm)
        except Exception:
            verdict = None
        if verdict is True:
            meta["verified"] += 1
        elif verdict is False:
            findings.append(_sv_finding(
                f"DOI '{norm}' was not found in CrossRef — confirm it is correct and not fabricated.",
                "Check the DOI at https://doi.org; correct or remove the source."))
            events.append(("invalid_doi", norm))
        else:
            meta["unverified"] += 1

    if events:
        try:
            from agent.analytics import emit  # noqa: PLC0415
            for kind, val in events:
                emit("citation_rejected", None, {"kind": kind, "citation": str(val)})
        except Exception:
            pass

    return {"name": "source_verification", "weight": 0.10,
            "score": round(max(0.0, 1.0 - 0.1 * len(findings)), 3),
            "findings": findings, "meta": meta}


def coherence_dimension(context_store: dict) -> dict:
    """Cross-chapter coherence (M3↔M4↔M5, roadmap #6): the safety net over
    persisted state for prose that entered without passing the M5 chat gate
    (auto-draft, editor PATCH, legacy). Hard findings (a prose number
    contradicting the persisted result) flow into `blocking`; everything else
    is advisory. Lazy import + never crashes. Weight 0.10."""
    findings: list[dict] = []
    try:
        from agent.coherence import validate_coherence  # noqa: PLC0415
        agg = validate_coherence(context_store)
        for f in agg["findings"]:
            findings.append({
                "issue": f["message"],
                "fix": "Quote the persisted analysis result verbatim, or reconcile the analysis and the "
                       "prose so they agree.",
                "chapter": (f.get("location") or {}).get("chapter") or "results",
                "severity": f["severity"]})
    except Exception:
        logger.exception("coherence_dimension failed (fail-open)")
    hard = sum(1 for f in findings if f["severity"] == "hard")
    soft = sum(1 for f in findings if f["severity"] == "soft")
    return {"name": "coherence", "weight": 0.10,
            "score": round(max(0.0, 1.0 - 0.5 * hard - 0.1 * soft), 3), "findings": findings}


def similarity_dimension(context_store: dict) -> dict:
    """Similarity & quote-hygiene self-check (roadmap #11): verbatim overlap with
    the project's OWN sources + chapter-to-chapter duplication. All findings soft
    — a match is evidence, not proof, and this is a self-check, not Turnitin (so
    it never blocks). Lazy import + never crashes. Weight 0.10."""
    findings: list[dict] = []
    try:
        from quality.similarity import similarity_findings  # noqa: PLC0415
        findings = similarity_findings(context_store)
    except Exception:
        logger.exception("similarity_dimension failed (fail-open)")
    src = sum(1 for f in findings if "duplicates" not in f["issue"])
    intra = len(findings) - src
    return {"name": "similarity", "weight": 0.10,
            "score": round(max(0.0, 1.0 - 0.10 * src - 0.05 * intra), 3), "findings": findings}


def score_thesis(context_store: dict, *, institution_profile: dict | None = None,
                 advisor_feedback: list[dict] | None = None, doi_verifier=None,
                 include_judge: bool = True) -> dict:
    """Full RubricResult. `include_judge=False` skips the two LLM judge dims
    (methodology/writing) entirely — a fully deterministic, offline scoring used
    by the committee-readiness certificate (roadmap #12), which must never make
    an LLM call by default."""
    method = _detect_method(context_store)
    dims = deterministic_dimensions(context_store)
    # Method-aware results-reporting checklist (PLS/CB-SEM/SPSS/generic).
    dims.append(results_validity_dimension(context_store, method))
    # Bounded LLM-judge dims: methodology (gap<->hypothesis trace) + writing
    # quality. Best-effort — a judge failure yields a neutral dim, never a crash.
    # Skipped entirely when include_judge=False (no LLM constructed).
    if include_judge:
        dims.append(judge_dimension("methodology", 0.15,
                                    _judge_prompt("methodology", context_store), context_store))
        dims.append(judge_dimension("writing", 0.10,
                                    _judge_prompt("writing", context_store), context_store))
    # Advisor-directive dim: open professor comments become hard findings on
    # their chapter. Read with an empty default so F3 works without F4.
    adv_dim, adv_summary = advisor_dimension(advisor_feedback or [])
    dims.append(adv_dim)
    # Methods pre-flight: soft, design-readiness gaps (sample/CMB/missing-data
    # plans) that should be caught before M4 — same check the live agent runs.
    dims.append(preflight_dimension(context_store))
    # Instrument quality: soft, item-level questionnaire issues (double-barreled
    # items, missing reverse-coded coverage, no attention check) caught before
    # fielding — same lint the live audit_instrument tool runs.
    dims.append(instrument_quality_dimension(context_store))
    # Stats self-validation: correctness (not presence) of the reported numbers.
    # Hard findings (impossible/self-contradictory) flow into `blocking` below.
    dims.append(stats_validity_dimension(context_store))
    # Source verification: author/metadata sanity + opt-in DOI existence (soft).
    dims.append(source_verification_dimension(context_store, doi_verifier))
    # Cross-chapter coherence: prose numbers must match persisted results (hard).
    dims.append(coherence_dimension(context_store))
    # Similarity self-check: verbatim overlap w/ own sources + intra-thesis copy (soft).
    dims.append(similarity_dimension(context_store))
    # Institution overlay last — it can re-weight the dims above and add hard
    # requirements (min refs) before we compute overall/blocking.
    dims = apply_institution_overlay(dims, institution_profile, context_store)
    blocking = [f["issue"] for d in dims for f in d["findings"] if f["severity"] == "hard"]
    return {
        "overall": _weighted(dims), "method": method, "dimensions": dims,
        "advisor": adv_summary,
        "blocking": blocking,
    }


def _detect_method(context_store: dict) -> str:
    m = ((context_store.get("m3_design") or {}).get("methodology") or "").lower()
    if "pls" in m:
        return "pls-sem"
    if "cb-sem" in m or "amos" in m or "covariance" in m:
        return "cb-sem"
    if "regression" in m or "spss" in m or "anova" in m:
        return "spss"
    return "generic"
