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


# The whitelist. An op not in this dict does not run, full stop.
OPS = {
    "detect": _op_detect,
    "describe": _op_describe,
    "corr": _op_corr,
    "cronbach": _op_cronbach,
    "regression": _op_regression,
    "ttest": _op_ttest,
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
    return json.dumps({"table_kind": table_kind, "findings": findings}, ensure_ascii=False)


@tool
def run_stats(op: str, file: str, params: dict | None = None) -> str:
    """Run ONE whitelisted statistical operation on an uploaded data file.

    Ops: detect (schema introspection — always run this first), describe,
    corr, cronbach (params: items=[cols]), regression (params: y=col,
    x=[cols]), ttest (params: value=col, group=col). Free-form code is NOT
    an op — if an analysis you need is missing, say so instead of improvising.

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
    return json.dumps({"op": op, **result}, ensure_ascii=False)
