"""Assumption-driven method advisor — pure, deterministic, ADVISORY ONLY.

Answers "is the analysis method you chose actually defensible for YOUR data and
model?" with a citable evidence row per criterion, instead of taking the
student's (or the model's) word for it.

Two modes: **design-time** (no data file — n comes from sample_plan.target_n;
distribution/missingness report `unknown`) and **data-time** (n = data rows,
distribution computed). Ranking is lexicographic over
(strongly_against, against, -favors) with a parsimony tie-break — never weights.

NOTHING here is ever hard: choosing an estimator is a judgment call, and the #1
bar reserves blocking for provably-wrong numbers. The conflict check surfaces as
soft preflight/rubric advice.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

METHODS = ("regression", "pls_sem", "cb_sem", "nonparametric")  # parsimony order
_V_ORDER = {"strongly_against": 0, "against": 1, "neutral": 2, "favors": 3, "unknown": 4}


def normalize_method(raw) -> Optional[str]:
    """Keyword mapping shared with sampling/instrument. None = unmapped."""
    if not isinstance(raw, str):
        return None
    m = raw.lower()
    if any(t in m for t in ("cb-sem", "cbsem", "amos", "lavaan", "covariance")):
        return "cb_sem"
    if "pls" in m:
        return "pls_sem"
    if "regress" in m or "spss" in m:
        return "regression"
    if "nonparam" in m or "non-param" in m:
        return "nonparametric"
    return None


def _row(criterion, observed, threshold, verdicts, citation, source) -> dict:
    return {"criterion": criterion, "observed": observed, "threshold": threshold,
            "verdicts": verdicts, "citation": citation, "source": source}


def model_profile(conceptual_model: dict, instrument: dict | None = None) -> dict:
    """Latent structure facts the decision table needs."""
    cm = conceptual_model if isinstance(conceptual_model, dict) else {}
    nodes = [n for n in (cm.get("nodes") or []) if isinstance(n, dict)]
    edges = cm.get("edges") or cm.get("paths") or []
    items_per = {}
    for n in nodes:
        items_per[n.get("label") or n.get("id")] = len(n.get("questions") or [])
    if not items_per and cm.get("constructs"):
        items_per = {c: 0 for c in cm["constructs"] if isinstance(c, str)}
    multi = [c for c, k in items_per.items() if k >= 2]
    single = [c for c, k in items_per.items() if k == 1]
    indeg: dict = {}
    for e in edges:
        if isinstance(e, dict):
            t = e.get("target") or e.get("to")
            if t:
                indeg[t] = indeg.get(t, 0) + 1
    has_mod = any(isinstance(n, dict) and "moder" in str(n.get("type") or n.get("nodeType") or "").lower()
                  for n in nodes) or bool(cm.get("moderator"))
    # A mediation shape: some construct is both a target and a source.
    srcs = {e.get("source") or e.get("from") for e in edges if isinstance(e, dict)}
    tgts = {e.get("target") or e.get("to") for e in edges if isinstance(e, dict)}
    has_med = bool(srcs & tgts)
    natures = {str((n.get("nature") or "")).lower() for n in nodes} - {""}
    return {"n_constructs": len(items_per), "multi_item": multi, "single_item": single,
            "has_latent": bool(multi), "max_in_degree": max(indeg.values()) if indeg else 0,
            "has_mediation": has_med, "has_moderation": has_mod,
            "formative": "formative" in natures, "nature_known": bool(natures)}


def advise(*, profile: dict, n: Optional[int], distribution: Optional[dict] = None,
           power_analysis: Optional[dict] = None, mcar_p: Optional[float] = None,
           missing_pct: Optional[float] = None, likert_levels: Optional[int] = None,
           goal: Optional[str] = None, chosen: Optional[str] = None,
           mode: str = "design", source_note: str = "") -> dict:
    ev: list[dict] = []
    unknown: list[str] = []
    caveats: list[str] = []

    # C1 latent measurement model
    if profile["has_latent"]:
        ev.append(_row("latent_model", {"multi_item_constructs": len(profile["multi_item"])},
                       "≥1 multi-item construct → a measurement model exists",
                       {"pls_sem": "favors", "cb_sem": "favors", "regression": "against"},
                       "Hair et al. (2022)", "conceptual_model"))
    else:
        ev.append(_row("latent_model", {"multi_item_constructs": 0},
                       "no multi-item construct → nothing to estimate a measurement model on",
                       {"regression": "favors", "pls_sem": "against", "cb_sem": "against"},
                       "Hair et al. (2022)", "conceptual_model"))

    # C2 formative
    if profile["formative"]:
        ev.append(_row("formative_constructs", {"formative": True}, "any formative construct",
                       {"cb_sem": "strongly_against", "pls_sem": "favors"},
                       "Hair et al. (2022)", "conceptual_model"))
    elif not profile["nature_known"]:
        unknown.append("construct_nature")
        caveats.append("Construct nature (reflective/formative) not declared — confirm before "
                       "finalizing the estimator.")

    # C3 CB-SEM sample floor
    if n is not None:
        if n < 100:
            ev.append(_row("cb_sem_sample_floor", {"n": n},
                           "CB-SEM defensible from n ≈ 150; never below ~100",
                           {"cb_sem": "strongly_against"}, "Kline (2016); Hair et al. (2019)", source_note))
        elif n < 150:
            ev.append(_row("cb_sem_sample_floor", {"n": n},
                           "CB-SEM defensible from n ≈ 150", {"cb_sem": "against"},
                           "Kline (2016)", source_note))
    else:
        unknown.append("sample_size")

    # C4 power adequacy
    req = (power_analysis or {}).get("recommended_n") or (power_analysis or {}).get("required_n")
    if n is not None and isinstance(req, int):
        if n < req:
            cites = "; ".join((power_analysis or {}).get("citations") or ["Cohen (1988)"])
            caveats.append(f"n = {n} is below the a-priori power-based N = {req} — disclose in "
                           f"limitations (source: sample_plan.power_analysis).")
            ev.append(_row("power_adequacy", {"n": n, "required_n": req},
                           "n ≥ the a-priori required N", {"cb_sem": "against", "pls_sem": "against"},
                           cites, "sample_plan.power_analysis"))
    elif req is None:
        unknown.append("power_analysis")

    # C5 10x rule
    if n is not None and profile["max_in_degree"]:
        ten = 10 * profile["max_in_degree"]
        ev.append(_row("ten_times_rule", {"n": n, "rule_n": ten}, f"n ≥ 10 × max arrows ({ten})",
                       {"pls_sem": "favors" if n >= ten else "against"},
                       "Hair, Hult, Ringle & Sarstedt (2017)", source_note))

    # C6 normality
    if distribution and distribution.get("n_items"):
        pct = distribution.get("severe_pct", 0.0)
        if pct >= 25:
            ev.append(_row("normality", {"severe_pct": pct, "severe_n": distribution.get("severe_n"),
                                         "n_items": distribution.get("n_items")},
                           "|skew| > 2 or |kurtosis| > 7 on ≥ 25% of items",
                           {"cb_sem": "strongly_against", "pls_sem": "favors", "nonparametric": "favors"},
                           "Kline (2016); West, Finch & Curran (1995)",
                           "computed: thesis_stats.rigor.check_distribution"))
        else:
            ev.append(_row("normality", {"severe_pct": pct}, "< 25% of items severely non-normal",
                           {"cb_sem": "neutral", "pls_sem": "neutral"},
                           "West, Finch & Curran (1995)", "computed: thesis_stats.rigor.check_distribution"))
    else:
        unknown.append("normality (re-run after data upload)")

    # C7 missingness / MCAR — note only
    if mcar_p is not None and mcar_p < 0.05:
        caveats.append("Little's MCAR test was rejected: FIML (a CB-SEM estimator) handles this in "
                       "principle (Enders & Bandalos 2001), but this tool applies neither FIML nor "
                       "multiple imputation in v1 — disclose the pattern.")
    if missing_pct is not None and missing_pct > 15:
        caveats.append(f"Missingness is high ({missing_pct}%) — treatment choice will be questioned.")

    # C8 mediation / moderation
    if profile["has_mediation"] or profile["has_moderation"]:
        ev.append(_row("mediation_moderation",
                       {"mediation": profile["has_mediation"], "moderation": profile["has_moderation"]},
                       "indirect/interaction effects hypothesized",
                       {"pls_sem": "favors", "regression": "neutral", "cb_sem": "neutral"},
                       "Hayes (2018); Preacher & Hayes (2008)", "conceptual_model"))

    # C9 single-item constructs
    if profile["single_item"]:
        ev.append(_row("single_item_constructs", {"constructs": profile["single_item"]},
                       "any single-item latent construct", {"cb_sem": "against"},
                       "Hair et al. (2022); Diamantopoulos et al. (2012)", "conceptual_model"))

    # C10 scale type
    if likert_levels is not None:
        if likert_levels < 5:
            ev.append(_row("scale_type", {"likert_levels": likert_levels},
                           "≥ 5 ordered categories to treat as approximately continuous",
                           {"cb_sem": "against"}, "Rhemtulla, Brosseau-Liard & Savalei (2012)", source_note))
    elif mode == "data":
        unknown.append("scale_type")

    # C11 goal
    if goal in ("confirmation", "prediction"):
        ev.append(_row("research_goal", {"goal": goal}, "confirmation → CB-SEM; prediction → PLS-SEM",
                       {"cb_sem": "favors"} if goal == "confirmation" else {"pls_sem": "favors"},
                       "Kline (2016); Hair et al. (2022)", "goal argument"))
    else:
        unknown.append("research_goal")

    # C12 nonparametric niche
    np_favored = (not profile["has_latent"]) and bool(
        distribution and distribution.get("severe_pct", 0) >= 25)
    ev.append(_row("nonparametric_niche", {"has_latent": profile["has_latent"]},
                   "no latent model AND severe non-normality",
                   {"nonparametric": "favors" if np_favored else "against"},
                   "Green (1991)", "conceptual_model + distribution"))

    # --- ranking (lexicographic, parsimony tie-break) ---
    tallies = {m: {"favors": 0, "against": 0, "strongly_against": 0} for m in METHODS}
    for row in ev:
        for m, v in row["verdicts"].items():
            if v in tallies.get(m, {}):
                tallies[m][v] += 1
    ranked = sorted(METHODS, key=lambda m: (tallies[m]["strongly_against"], tallies[m]["against"],
                                            -tallies[m]["favors"], METHODS.index(m)))
    recommendation = [{"method": m, "rank": i + 1, "tally": tallies[m]} for i, m in enumerate(ranked)]

    advised = ranked[0]
    conflict = None
    if chosen and chosen != advised:
        reasons = [r["criterion"] for r in ev
                   if r["verdicts"].get(chosen) in ("against", "strongly_against")]
        if reasons:
            conflict = {"chosen": chosen, "advised": advised, "reasons": reasons,
                        "sentence": (f"The design chose {chosen}, but {', '.join(reasons)} count against it "
                                     f"for this data/model; {advised} is the evidence-backed alternative.")}

    return {
        "mode": mode,
        "recommendation": recommendation,
        "evidence": ev,
        "unknown": unknown,
        "caveats": caveats,
        "conflict_with_choice": conflict,
        "citations": sorted({r["citation"] for r in ev}),
        "method": "deterministic decision table v1 (no LLM)",
    }


def fingerprint(*parts) -> str:
    return "sha1:" + hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]
