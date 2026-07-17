"""Dothesis-shape adapters for the thesis-stats self-validation layer.

Pure — no LangChain, no tools, no I/O. Normalizes dothesis-specific payloads
(the summarized `run_stats` op returns and the persisted `analysis_results`
block) into thesis-stats *claims*, then runs the shared deterministic checks.
Never raises out of a public entry point (fail-open — a validator bug must never
block a legitimate thesis). See design spec §3.1, §6.4, §7.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _lib():
    # Lazy — the engine is installed editable but keep the import off module load.
    from thesis_stats.validation import (  # noqa: PLC0415
        aggregate, claims_from_rigor, claims_from_table, make_claim, validate_claims,
    )
    return aggregate, claims_from_rigor, claims_from_table, make_claim, validate_claims


def _norm_path(p: Any) -> Optional[str]:
    if not isinstance(p, str):
        return None
    return p.replace("→", "->").replace("  ", " ").replace(" -> ", " -> ").strip()


def _p_value(v):
    """Return (value, threshold_flag). '<0.001' → (0.001, 0.001)."""
    if isinstance(v, str) and v.strip().startswith("<"):
        try:
            return float(v.strip().lstrip("< ").replace("p", "")), True
        except ValueError:
            return None, False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), False
    return None, False


def _agg(findings: list[dict], *, crashed: bool = False) -> dict:
    hard = [f for f in findings if f.get("severity") == "hard"]
    soft = [f for f in findings if f.get("severity") == "soft"]
    return {"passed": not hard, "hard": len(hard), "soft": len(soft),
            "findings": findings, "findings_hard": hard, "findings_soft": soft,
            "crashed": crashed}


# ============================================================================
# run_stats op summaries → claims
# ============================================================================

def claims_from_run_stats(op: str, summary: dict) -> list[dict]:
    if not isinstance(summary, dict):
        return []
    _agg_, claims_from_rigor, _tbl, mk, _vc = _lib()
    claims: list[dict] = []

    if op in ("pls_sem", "moderation"):
        claims += _pls_summary_claims(summary, mk)
    elif op == "efa":
        if summary.get("kmo") is not None:
            claims.append(mk("kmo", summary["kmo"], table="efa"))
        if summary.get("bartlett_p") is not None:
            claims.append(mk("p", summary["bartlett_p"], table="efa", flags={"is_p": True}))
        if summary.get("total_variance_explained") is not None:
            claims.append(mk("variance_pct", summary["total_variance_explained"], table="efa"))
    elif op == "regression_full":
        claims += _regression_dict_claims(summary.get("regression"), mk)
    elif op == "regression":
        claims += _basic_regression_claims(summary, mk)
    elif op == "cronbach":
        if summary.get("alpha") is not None:
            claims.append(mk("alpha", summary["alpha"], table="reliability"))
    elif op == "corr":
        for c1, row in (summary.get("correlations") or {}).items():
            for c2, v in (row or {}).items():
                if c1 != c2 and isinstance(v, (int, float)):
                    claims.append(mk("corr", v, construct=f"{c1}-{c2}", table="correlations"))
    elif op == "rigor":
        claims += claims_from_rigor(summary, source="computed")
    return claims


def _pls_summary_claims(summary: dict, mk) -> list[dict]:
    claims: list[dict] = []
    for path, row in (summary.get("paths") or {}).items():
        p = _norm_path(path)
        if not isinstance(row, dict):
            continue
        if row.get("beta") is not None:
            claims.append(mk("beta", row["beta"], path=p, table="structural_model"))
        if row.get("t") is not None:
            claims.append(mk("t", row["t"], path=p, table="structural_model"))
        ci = row.get("ci95")
        if isinstance(ci, (list, tuple)) and len(ci) == 2:
            claims.append(mk("ci", values=list(ci), path=p, table="structural_model"))
    for con, row in (summary.get("reliability") or {}).items():
        if not isinstance(row, dict):
            continue
        for key, metric in (("r_squared", "r2"), ("ave", "ave"),
                            ("cronbach_alpha", "alpha"), ("cr_rho", "cr")):
            if row.get(key) is not None:
                table = "structural_model" if metric == "r2" else "measurement_model"
                claims.append(mk(metric, row[key], construct=con, table=table))
    for item, v in (summary.get("outer_loadings") or {}).items():
        if isinstance(v, (int, float)):
            claims.append(mk("loading", v, item=item, table="measurement_model"))
    for c1, row in (summary.get("htmt") or {}).items():
        for c2, v in (row or {}).items():
            if c1 != c2 and isinstance(v, (int, float)) and v != 0:
                claims.append(mk("htmt", v, construct=f"{c1}-{c2}", table="discriminant_validity"))
    for c1, row in (summary.get("fornell_larcker") or {}).items():
        for c2, v in (row or {}).items():
            if not isinstance(v, (int, float)):
                continue
            if c1 == c2:
                claims.append(mk("fornell_larcker_diag", v, construct=c1, table="discriminant_validity"))
            else:
                claims.append(mk("corr", v, construct=f"{c1}-{c2}", table="discriminant_validity"))
    vif = summary.get("vif") or {}
    for con, row in (vif.get("outer_vif") or {}).items():
        for item, v in (row or {}).items():
            if isinstance(v, (int, float)):
                claims.append(mk("vif", v, construct=con, item=item, table="collinearity"))
    for target, row in (vif.get("inner_vif") or {}).items():
        for srcn, v in (row or {}).items():
            if isinstance(v, (int, float)):
                claims.append(mk("vif", v, path=_norm_path(f"{srcn} -> {target}"), table="collinearity"))
    for path, v in (summary.get("f_squared") or {}).items():
        if isinstance(v, (int, float)):
            claims.append(mk("f2", v, path=_norm_path(path), table="structural_model"))
    if isinstance(summary.get("goodness_of_fit"), (int, float)):
        claims.append(mk("gof", summary["goodness_of_fit"], table="model_fit"))
    return claims


def _regression_dict_claims(rr: Any, mk) -> list[dict]:
    if not isinstance(rr, dict):
        return []
    claims: list[dict] = []
    target = rr.get("target_variable")
    n = rr.get("n_observations")
    coefs = rr.get("coefficients") or []
    k = max(len([c for c in coefs if c.get("variable") not in ("(Constant)", "Intercept")]), 1)
    df = (n - k - 1) if isinstance(n, int) else None
    if rr.get("r_squared") is not None:
        claims.append(mk("r2", rr["r_squared"], construct=target, n=n, table="structural_model"))
    if rr.get("adjusted_r_squared") is not None:
        claims.append(mk("r2_adj", rr["adjusted_r_squared"], construct=target, table="structural_model"))
    if isinstance(n, int):
        claims.append(mk("n", n, table="structural_model"))
    for c in coefs:
        var = c.get("variable")
        if var in ("(Constant)", "Intercept"):
            continue
        path = _norm_path(f"{var} -> {target}")
        sig = c.get("significance")
        flags = {"significant": sig != "ns"} if sig is not None else {}
        if c.get("coefficient") is not None:
            claims.append(mk("beta", c["coefficient"], path=path, table="structural_model"))
        if c.get("t_statistic") is not None:
            claims.append(mk("t", c["t_statistic"], path=path, df=df, table="structural_model"))
        if c.get("p_value") is not None:
            claims.append(mk("p", c["p_value"], path=path, df=df, table="structural_model", flags=flags))
    return claims


def _basic_regression_claims(summary: dict, mk) -> list[dict]:
    claims: list[dict] = []
    y = summary.get("y")
    n = summary.get("n")
    coefs = summary.get("coefficients") or {}
    k = max(len([name for name in coefs if name != "const"]), 1)
    df = (n - k - 1) if isinstance(n, int) else None
    if summary.get("r2") is not None:
        claims.append(mk("r2", summary["r2"], construct=y, n=n, table="structural_model"))
    if isinstance(n, int):
        claims.append(mk("n", n, table="structural_model"))
    for name, row in coefs.items():
        if name == "const" or not isinstance(row, dict):
            continue
        path = _norm_path(f"{name} -> {y}")
        if row.get("beta") is not None:
            claims.append(mk("beta", row["beta"], path=path, table="structural_model"))
        if row.get("t") is not None:
            claims.append(mk("t", row["t"], path=path, df=df, table="structural_model"))
        if row.get("p") is not None:
            claims.append(mk("p", row["p"], path=path, df=df, table="structural_model"))
    return claims


# ============================================================================
# Persisted analysis_results block → claims
# ============================================================================

def claims_from_analysis_results(block: Any) -> list[dict]:
    if not isinstance(block, dict):
        return []
    _agg_, _rigor, claims_from_table, mk, _vc = _lib()
    claims: list[dict] = []

    # Orchestrator {results: {step: StepResult{table}}} shape.
    if "results" in block and isinstance(block["results"], dict) and "measurement_model" not in block:
        for step in block["results"].values():
            if isinstance(step, dict) and isinstance(step.get("table"), list):
                kind = step.get("data_type") or step.get("step_name") or "table"
                claims += claims_from_table(kind, step["table"], source="parsed")
        return claims

    desc = block.get("descriptives")
    if isinstance(desc, dict):
        if isinstance(desc.get("n"), (int, float)):
            claims.append(mk("n", int(desc["n"]), table="descriptives"))
        for item in (desc.get("by_item") or []):
            if isinstance(item, dict) and item.get("sd") is not None:
                claims.append(mk("sd", item["sd"], item=item.get("item"), table="descriptives"))

    for con in (block.get("measurement_model") or []):
        if not isinstance(con, dict):
            continue
        name = con.get("construct")
        for it in (con.get("items") or []):
            if isinstance(it, dict) and it.get("loading") is not None:
                claims.append(mk("loading", it["loading"], construct=name, item=it.get("item"),
                                 table="measurement_model"))
        if con.get("ave") is not None:
            claims.append(mk("ave", con["ave"], construct=name, table="measurement_model"))
        if con.get("cronbach_alpha") is not None:
            claims.append(mk("alpha", con["cronbach_alpha"], construct=name, table="measurement_model"))
        if con.get("composite_reliability") is not None:
            claims.append(mk("cr", con["composite_reliability"], construct=name, table="measurement_model"))

    dv = block.get("discriminant_validity")
    if isinstance(dv, dict) and isinstance(dv.get("matrix"), list) and dv["matrix"]:
        claims += _matrix_claims(dv, mk)

    for ht in (block.get("hypothesis_tests") or []):
        if not isinstance(ht, dict):
            continue
        path = _norm_path(ht.get("path"))
        nums = ht.get("numbers") or {}
        decision = ht.get("decision")
        sig = None if decision is None else str(decision).lower().startswith("support")
        if nums.get("beta") is not None:
            claims.append(mk("beta", nums["beta"], path=path, table="hypothesis_tests"))
        if nums.get("t") is not None:
            claims.append(mk("t", nums["t"], path=path, table="hypothesis_tests"))
        if "p" in nums:
            pv, thr = _p_value(nums["p"])
            if pv is not None:
                flags = {"significant": sig} if sig is not None else {}
                if thr:
                    flags["p_threshold"] = pv
                claims.append(mk("p", pv, path=path, table="hypothesis_tests", flags=flags))
        if nums.get("f2") is not None:
            claims.append(mk("f2", nums["f2"], path=path, table="hypothesis_tests", source="parsed"))
        ac = ht.get("assumption_checks") or {}
        if ac.get("vif") is not None:
            claims.append(mk("vif", ac["vif"], path=path, table="collinearity"))

    sm = block.get("structural_model")
    if isinstance(sm, dict):
        for con, v in (sm.get("r2") or {}).items():
            if isinstance(v, (int, float)):
                claims.append(mk("r2", v, construct=con, table="structural_model"))
        # CB-SEM fit indices, when present (enables the PLS/CB-SEM family-mix check).
        for key in ("cfi", "tli", "rmsea", "srmr"):
            if isinstance(sm.get(key), (int, float)):
                claims.append(mk(key, sm[key], table="model_fit"))
    # Everything from a persisted block is treated as parsed precision.
    for c in claims:
        if c.get("source") == "computed":
            c["source"] = "parsed"
    return claims


def _matrix_claims(dv: dict, mk) -> list[dict]:
    matrix = dv["matrix"]
    labels = matrix[0]
    metric = "htmt" if str(dv.get("method", "")).upper() == "HTMT" else "corr"
    out = []
    for i, row in enumerate(matrix[1:]):
        if not isinstance(row, list):
            continue
        for j, v in enumerate(row):
            if i != j and isinstance(v, (int, float)) and j < len(labels) and i < len(labels):
                out.append(mk(metric, v, construct=f"{labels[i]}-{labels[j]}",
                              table="discriminant_validity", source="parsed"))
    return out


# ============================================================================
# Composite entry points (never raise)
# ============================================================================

def validate_run_stats(op: str, summary: dict) -> dict:
    try:
        _aggregate, _r, _t, _mk, validate_claims = _lib()
        return _agg(validate_claims(claims_from_run_stats(op, summary)))
    except Exception:
        logger.exception("validate_run_stats crashed for op=%s", op)
        return _agg([], crashed=True)


def validate_analysis_results(block: Any, m3_hypotheses: Optional[list] = None) -> dict:
    try:
        _a, _r, _t, mk, validate_claims = _lib()
        claims = claims_from_analysis_results(block)
        findings = validate_claims(claims)
        # Unstructured free-text results: cannot verify numbers.
        if isinstance(block, str) and block.strip():
            findings = findings + [{
                "check": "structure.unstructured", "severity": "soft",
                "message": "Results are stored as free text, so the numbers cannot be verified.",
                "location": {"table": "analysis_results", "construct": None, "item": None, "path": None},
                "observed": None, "expected": "structured analysis_results", "tolerance": None,
                "source": "parsed"}]
        # X2 hypothesis coverage (soft, structural count).
        if m3_hypotheses and isinstance(block, dict):
            covered = {str(ht.get("hypothesis")) for ht in (block.get("hypothesis_tests") or [])
                       if isinstance(ht, dict)}
            covered |= {str(ht.get("id")) for ht in (block.get("hypothesis_tests") or [])
                        if isinstance(ht, dict)}
            for h in m3_hypotheses:
                hid = str(h.get("id") if isinstance(h, dict) else h)
                if hid and hid not in covered:
                    findings.append({
                        "check": "xtable.hypothesis_coverage", "severity": "soft",
                        "message": f"Hypothesis {hid} has no result entry in the analysis.",
                        "location": {"table": "hypothesis_tests", "construct": None, "item": None, "path": None},
                        "observed": {"hypothesis": hid}, "expected": "a result for every hypothesis",
                        "tolerance": None, "source": "parsed"})
        return _agg(findings)
    except Exception:
        logger.exception("validate_analysis_results crashed")
        return _agg([], crashed=True)
