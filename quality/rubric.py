"""Rubric scorer: deterministic dimensions (reusing existing validators) + bounded
LLM-judge dimensions -> a RubricResult. Read-only over a nested context_store, so it
can never corrupt a thesis. institution_profile + advisor_feedback are read with safe
defaults (owned by the cross-session-memory spec)."""
from __future__ import annotations

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


def _weighted(dims: list[dict]) -> float:
    # Weights are illustrative and don't sum to 1; normalize by total weight so
    # institution overlays that change weights don't skew the 0..1 overall.
    total_w = sum(d["weight"] for d in dims) or 1.0
    return round(sum(d["score"] * d["weight"] for d in dims) / total_w, 3)


def score_thesis(context_store: dict, *, institution_profile: dict | None = None,
                 advisor_feedback: list[dict] | None = None) -> dict:
    """Full RubricResult. This task: deterministic dims only (judge + advisor + method
    overlay land in later tasks)."""
    method = _detect_method(context_store)
    dims = deterministic_dimensions(context_store)
    blocking = [f["issue"] for d in dims for f in d["findings"] if f["severity"] == "hard"]
    return {
        "overall": _weighted(dims), "method": method, "dimensions": dims,
        "advisor": {"total": 0, "addressed": 0, "open": []},
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
