"""M4 stats tool — whitelisted operations only.

Architecture §2.3 / v2 brief risk §8.1: free-form model-written Python over
user data is one prompt-injection away from arbitrary code. The whitelist IS
the security boundary — every op is a vetted function here; the model only
picks ops and parameters. In production these run inside the network-less
sandbox service; the spike runs them in-process for the CLI.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _load_df(file: str):
    import pandas as pd
    p = Path(file)
    if not p.exists():
        raise FileNotFoundError(f"data file not found: {file}")
    if p.suffix.lower() == ".sav":
        import pyreadstat
        df, _meta = pyreadstat.read_sav(str(p))
        return df
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)
    return pd.read_csv(p)


def _op_detect(file: str, **_: Any) -> dict:
    df = _load_df(file)
    return {
        "rows": int(df.shape[0]),
        "columns": [
            {
                "name": c,
                "dtype": str(df[c].dtype),
                "valid_n": int(df[c].notna().sum()),
                "example": None if df[c].dropna().empty else str(df[c].dropna().iloc[0]),
            }
            for c in df.columns
        ],
    }


def _op_describe(file: str, columns: list[str] | None = None, **_: Any) -> dict:
    df = _load_df(file)
    sub = df[columns] if columns else df.select_dtypes("number")
    desc = sub.describe().round(4)
    return {"describe": json.loads(desc.to_json())}


def _op_corr(file: str, columns: list[str] | None = None, **_: Any) -> dict:
    df = _load_df(file)
    sub = df[columns] if columns else df.select_dtypes("number")
    return {"correlations": json.loads(sub.corr().round(4).to_json())}


def _op_cronbach(file: str, items: list[str] = None, **_: Any) -> dict:
    """Cronbach's alpha over the given item columns (one construct)."""
    if not items or len(items) < 2:
        raise ValueError("cronbach needs ≥2 item columns")
    df = _load_df(file)[items].dropna()
    k = len(items)
    item_vars = df.var(axis=0, ddof=1)
    total_var = df.sum(axis=1).var(ddof=1)
    alpha = (k / (k - 1)) * (1 - item_vars.sum() / total_var)
    return {"items": items, "n": int(df.shape[0]), "alpha": round(float(alpha), 4)}


def _op_regression(file: str, y: str = None, x: list[str] = None, **_: Any) -> dict:
    """OLS y ~ x1 + … via scipy/numpy — betas, t, p, R²."""
    import numpy as np
    from scipy import stats as sps
    if not y or not x:
        raise ValueError("regression needs y and x")
    df = _load_df(file)[[y, *x]].dropna()
    X = np.column_stack([np.ones(len(df)), df[x].to_numpy(dtype=float)])
    Y = df[y].to_numpy(dtype=float)
    beta, _res, _rank, _sv = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ beta
    dof = len(Y) - X.shape[1]
    mse = float(resid @ resid) / dof
    se = (mse * np.linalg.inv(X.T @ X).diagonal()) ** 0.5
    t = beta / se
    p = 2 * (1 - sps.t.cdf(abs(t), dof))
    r2 = 1 - float(resid @ resid) / float(((Y - Y.mean()) ** 2).sum())
    coef = {
        name: {"beta": round(float(b), 4), "se": round(float(s), 4),
               "t": round(float(tv), 3), "p": round(float(pv), 5)}
        for name, b, s, tv, pv in zip(["const", *x], beta, se, t, p)
    }
    return {"y": y, "n": int(len(df)), "r2": round(r2, 4), "coefficients": coef}


def _op_ttest(file: str, value: str = None, group: str = None, **_: Any) -> dict:
    from scipy import stats as sps
    if not value or not group:
        raise ValueError("ttest needs value and group columns")
    df = _load_df(file)[[value, group]].dropna()
    levels = df[group].unique()
    if len(levels) != 2:
        raise ValueError(f"group column has {len(levels)} levels; need exactly 2")
    a = df[df[group] == levels[0]][value]
    b = df[df[group] == levels[1]][value]
    t, p = sps.ttest_ind(a, b, equal_var=False)
    return {
        "groups": {str(levels[0]): {"n": int(len(a)), "mean": round(float(a.mean()), 4)},
                   str(levels[1]): {"n": int(len(b)), "mean": round(float(b.mean()), 4)}},
        "t": round(float(t), 3), "p": round(float(p), 5),
    }


# --- thesis-stats-backed ops (real PLS-SEM / EFA / mediation / moderation) ---
# These compute the numbers a quantitative thesis needs from the RAW uploaded
# data via the shared thesis-stats engine, run IN-PROCESS (no network, no
# subprocess). thesis_stats is imported lazily so a missing install degrades to
# the existing "stats dependency missing" JSON error. Results are SUMMARIZED to
# a bounded, construct-level payload (never row-level matrices) — the LLM needs
# tables, not n×k floats.

_BOOTSTRAP_CAP = 1000


def _round_floats(obj: Any, nd: int = 4):
    if isinstance(obj, dict):
        return {k: _round_floats(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, nd) for v in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def _records(file: str) -> list[dict]:
    return _load_df(file).to_dict("records")


def _adapt(conceptual_model, measurement):
    from agent.tools.model_adapter import to_advance_model
    if not conceptual_model:
        raise ValueError("this op needs a conceptual_model (params.conceptual_model)")
    return to_advance_model(conceptual_model, measurement=measurement)


def _summarize_pls(raw: dict, bootstrap_samples: int) -> dict:
    boot_paths = (raw.get("raw_bootstrap") or {}).get("paths") or {}
    paths: dict = {}
    for target, sources in (raw.get("raw_path_coefficients") or {}).items():
        for source, coef in (sources or {}).items():
            if coef is None or abs(float(coef)) < 1e-12:
                continue
            key = f"{source} -> {target}"
            entry = {"beta": round(float(coef), 4)}
            b = boot_paths.get(key)
            if b:
                entry["t"] = round(float(b.get("t stat.") or 0.0), 3)
                entry["ci95"] = [round(float(b.get("perc.025") or 0.0), 4),
                                 round(float(b.get("perc.975") or 0.0), 4)]
            paths[key] = entry

    inner = raw.get("raw_inner_summary") or {}
    uni = raw.get("raw_unidimensionality") or {}
    reliability = {
        c: {
            "r_squared": round(float(s.get("r_squared", 0.0)), 4),
            "ave": round(float(s.get("ave", 0.0)), 4),
            "cronbach_alpha": round(float((uni.get(c) or {}).get("cronbach_alpha", 0.0)), 4),
            "cr_rho": round(float((uni.get(c) or {}).get("dillon_goldstein_rho", 0.0)), 4),
        }
        for c, s in inner.items()
    }
    loadings = {item: round(float(v.get("loading", 0.0)), 4)
                for item, v in (raw.get("raw_outer_model") or {}).items()}

    return {
        "paths": paths,
        "reliability": reliability,
        "outer_loadings": loadings,
        "htmt": _round_floats(raw.get("raw_htmt")),
        "fornell_larcker": _round_floats(raw.get("raw_fornell_larcker")),
        "vif": _round_floats(raw.get("raw_vif")),
        "f_squared": _round_floats(raw.get("raw_f_squared")),
        "goodness_of_fit": round(float(raw.get("raw_goodness_of_fit") or 0.0), 4),
        "bootstrap_samples": bootstrap_samples,
    }


def _op_pls_sem(file: str, conceptual_model=None, measurement=None,
                bootstrap_samples: int = 500, **_: Any) -> dict:
    import thesis_stats as ts
    bs = max(0, min(int(bootstrap_samples), _BOOTSTRAP_CAP))
    model = _adapt(conceptual_model, measurement)
    raw = ts.run_pls(model, _records(file), bootstrap_samples=bs)
    return _summarize_pls(raw, bs)


def _op_efa(file: str, conceptual_model=None, measurement=None, **_: Any) -> dict:
    import thesis_stats as ts
    model = _adapt(conceptual_model, measurement)
    raw = ts.run_spss_basic(model, _records(file))
    efa = raw.get("efa_result") or {}
    return {
        "kmo": round(float(efa.get("kmo_measure", 0.0)), 4) if efa else None,
        "bartlett_p": efa.get("bartlett_p_value"),
        "total_variance_explained": efa.get("total_variance_explained"),
        "factors": _round_floats(efa.get("factors")) if efa else None,
    }


def _op_regression_full(file: str, conceptual_model=None, measurement=None, **_: Any) -> dict:
    import thesis_stats as ts
    model = _adapt(conceptual_model, measurement)
    raw = ts.run_spss_regression(model, _records(file))
    return {"regression": _round_floats(raw.get("regression_result"))}


def _op_mediation(file: str, conceptual_model=None, measurement=None,
                  bootstrap_samples: int = 500, **_: Any) -> dict:
    import thesis_stats as ts
    bs = max(0, min(int(bootstrap_samples), _BOOTSTRAP_CAP))
    model = _adapt(conceptual_model, measurement)
    raw = ts.run_pls(model, _records(file), bootstrap_samples=bs)
    return {"effects": _round_floats(raw.get("raw_effects")), "bootstrap_samples": bs}


def _op_moderation(file: str, conceptual_model=None, measurement=None,
                   bootstrap_samples: int = 500, **_: Any) -> dict:
    import thesis_stats as ts
    bs = max(0, min(int(bootstrap_samples), _BOOTSTRAP_CAP))
    model = _adapt(conceptual_model, measurement)
    raw = ts.run_pls(model, _records(file), bootstrap_samples=bs)
    summary = _summarize_pls(raw, bs)
    interactions = {k: v for k, v in summary["paths"].items() if "*" in k}
    if not interactions:
        return {"error": "no interaction term found — encode the moderator in the "
                         "conceptual_model (decomposition shape with a 'moderator', or a "
                         "moderate_effect node)", "paths": summary["paths"]}
    return {"interactions": interactions, "all_paths": summary["paths"],
            "f_squared": summary["f_squared"], "bootstrap_samples": bs}


def _op_rigor(file: str, conceptual_model=None, measurement=None, group=None,
              regressions=None, checks=None, **_: Any) -> dict:
    import thesis_stats as ts
    model = None
    if conceptual_model:
        model = _adapt(conceptual_model, measurement)
    out = ts.run_rigor(_records(file), model=model, groups=group,
                       regressions=regressions, checks=checks)
    return _round_floats(out)


def _op_power(file: str = "", analysis: str = None, mode: str = "apriori",
              effect_size=None, alpha: float = 0.05, power: float = 0.80,
              predictors=None, n=None, n1=None, n2=None, ratio: float = 1.0,
              alternative: str = "two-sided", **_: Any) -> dict:
    """A-priori / post-hoc / sensitivity power. `file` is optional: a-priori is
    data-free; for post-hoc/sensitivity, n defaults to the uploaded file's row
    count when omitted (the one data-touching convenience)."""
    import thesis_stats as ts
    if mode != "apriori" and n is None and file:
        try:
            n = int(_load_df(file).shape[0])
        except Exception:
            n = None
    return _round_floats(ts.run_power(
        analysis, mode, effect_size=effect_size, alpha=alpha, power=power,
        predictors=predictors, n=n, n1=n1, n2=n2, ratio=ratio, alternative=alternative))


# The whitelist. An op not in this dict does not run, full stop.
OPS = {
    "detect": _op_detect,
    "describe": _op_describe,
    "corr": _op_corr,
    "cronbach": _op_cronbach,
    "regression": _op_regression,
    "ttest": _op_ttest,
    # thesis-stats-backed (compute from raw data, not parsed from pasted output)
    "pls_sem": _op_pls_sem,
    "efa": _op_efa,
    "regression_full": _op_regression_full,
    "mediation": _op_mediation,
    "moderation": _op_moderation,
    "rigor": _op_rigor,
    "power": _op_power,
}


# --- Output sanity layer (F8 Task 4) -------------------------------------
# check_thresholds classifies numbers the STUDENT already pasted (from SmartPLS/
# SPSS output) against standard reporting thresholds. It is deliberately NOT a
# run_stats op: it computes NOTHING — every branch here is a comparison, never
# arithmetic on a value — so it can safely run on typed-in tables the sandbox
# never saw. The full threshold table + narration guidance lives in
# skills/dothesis-m4-analysis/references/output-interpretation.md.
_THRESHOLDS = {
    "loadings": lambda v: None if v >= 0.708 else "below 0.708 — consider removing this item",
    "ave": lambda v: None if v >= 0.5 else "AVE below 0.5 — convergent validity not met",
    "cr": lambda v: None if 0.7 <= v <= 0.95 else "CR outside 0.7–0.95",
    "htmt": lambda v: None if v < 0.85 else "HTMT ≥ 0.85 — discriminant validity may fail",
    "vif": lambda v: None if v < 3.3 else "VIF ≥ 3.3 — possible collinearity",
}


@tool
def check_thresholds(table_kind: str, rows: list[dict]) -> str:
    """Classify a pasted results table (loadings/ave/cr/htmt/vif) against standard
    thresholds and flag both violations AND suspiciously-perfect patterns (all
    loadings > 0.9 ⇒ possible straight-lined data). Does NOT compute new
    statistics — it only compares the values you paste in.

    Args:
        table_kind: One of loadings, ave, cr, htmt, vif.
        rows: List of {"item"/"pair": label, "value": number} from the student's
            SmartPLS/SPSS output.
    """
    check = _THRESHOLDS.get(table_kind)
    findings = []
    values = [r.get("value") for r in rows if isinstance(r.get("value"), (int, float))]
    if check:
        for r in rows:
            v = r.get("value")
            msg = check(v) if isinstance(v, (int, float)) else None
            if msg:
                findings.append({"issue": f"{r.get('item') or r.get('pair') or '?'}: {msg}",
                                 "severity": "hard"})
    # Suspiciously perfect: a whole construct of loadings above 0.9 is more often
    # bad data (straight-lining, a copied matrix) than a genuinely clean scale.
    # min() SELECTS a value; it derives no new statistic.
    if table_kind == "loadings" and values and min(values) >= 0.9:
        findings.append({"issue": "All loadings > 0.9 — suspiciously perfect; check for "
                                  "straight-lined data or a wrong matrix.", "severity": "soft"})
    # Verification arithmetic (thesis-stats): catch impossible/self-contradictory
    # values the compare-only thresholds cannot see (e.g. a pasted loading > 1, or
    # a t/p pair that is arithmetically impossible). Fail-open. Still findings-only.
    try:
        from thesis_stats.validation import claims_from_table, validate_claims
        for f in validate_claims(claims_from_table(table_kind, rows, source="parsed")):
            findings.append({"issue": f["message"], "severity": f["severity"], "check": f["check"]})
    except Exception:
        logger.exception("check_thresholds validation failed (fail-open)")
    return json.dumps({"table_kind": table_kind, "findings": findings}, ensure_ascii=False)


@tool
def run_stats(op: str, file: str, params: dict | None = None) -> str:
    """Run ONE whitelisted statistical operation on an uploaded data file.

    Basic ops: detect (schema introspection — always run this first), describe,
    corr, cronbach (params: items=[cols]), regression (params: y=col, x=[cols]),
    ttest (params: value=col, group=col).

    Model-based ops (compute real PLS-SEM/EFA from the RAW data — pass
    params.conceptual_model, and params.measurement={construct: [cols]} when the
    model's questions are item texts rather than column names):
      pls_sem  — full PLS-SEM: path betas (+bootstrap t/CI), R², outer loadings,
                 AVE/CR/alpha, HTMT, Fornell-Larcker, VIF, f², GoF
                 (params: conceptual_model, measurement, bootstrap_samples≤1000)
      efa      — EFA: KMO, Bartlett, factors (params: conceptual_model, measurement)
      regression_full — OLS toward the dependent construct (F-test, R², coeffs)
      mediation — direct/indirect/total effects (params: …, bootstrap_samples)
      moderation — interaction path from a moderated model (needs a moderator in
                 the conceptual_model)
      rigor    — assumptions + effect sizes + Harman CMB (params: group=col,
                 regressions=[{y,x}], checks=[...])
      power    — sample-size power analysis, data-free for a-priori (params:
                 analysis=regression|correlation|ttest|pls_sem, mode=apriori|
                 posthoc|sensitivity, effect_size (num or small/medium/large),
                 alpha=.05, power=.80, predictors, n) → required_n / achieved_power
                 / mdes + a committee-ready justification sentence

    Free-form code is NOT an op — if an analysis you need is missing, say so
    instead of improvising.

    Args:
        op: One of the whitelisted operation names.
        file: Path to the uploaded data file (.csv, .xlsx, .sav).
        params: Op-specific parameters (see op list).
    """
    fn = OPS.get(op)
    if fn is None:
        return json.dumps({
            "error": f"op {op!r} is not whitelisted",
            "available": sorted(OPS),
        })
    try:
        result = fn(file, **(params or {}))
    except ModuleNotFoundError as e:
        return json.dumps({"error": f"stats dependency missing: {e.name} — install pandas/scipy/pyreadstat"})
    except Exception as e:
        logger.exception("run_stats %s failed", op)
        return json.dumps({"error": f"{op} failed: {e}"})
    # Self-validation: attach (never withhold) findings so the agent can explain
    # a problem; the hard BLOCK happens at the M4 commit gate. Fail-open (§8).
    if isinstance(result, dict):
        try:
            from agent.stats_validation import validate_run_stats
            v = validate_run_stats(op, result)
            if v.get("findings"):
                result["validation"] = {"passed": v["passed"], "hard": v["hard"],
                                        "soft": v["soft"], "findings": v["findings"]}
        except Exception:
            logger.exception("run_stats validation failed for %s (fail-open)", op)
    return json.dumps({"op": op, **result}, ensure_ascii=False)
