"""SPSS paste-text parser — regex extractors for common SPSS output tables.

Each step extractor reads the user's pasted SPSS output and returns a
StepResult-shaped dict. On regex miss, returns None so the dispatcher
falls back to LLM extraction.
"""
from __future__ import annotations

import re


# Cronbach pairs (alpha, N items) and the immediately-following "Construct:" label.
# The golden fixture places the Construct: label AFTER the alpha/N line, so the
# regex scans forward: alpha line → optional blank/separator lines → Construct:.
_CRONBACH_BLOCK = re.compile(
    r"Cronbach's\s+Alpha\s+N\s+of\s+Items\s+"
    r"(?P<alpha>\.\d+|\d+\.\d+)\s+(?P<n>\d+)\s+"
    r"Construct:\s*(?P<construct>[^\n]+)",
    re.IGNORECASE,
)


def _extract_cronbach(text: str) -> dict | None:
    matches = list(_CRONBACH_BLOCK.finditer(text))
    if not matches:
        return None
    rows = []
    all_meet = True
    for m in matches:
        alpha = float(m.group("alpha"))
        if alpha < 0.7:
            all_meet = False
        rows.append({
            "construct": m.group("construct").strip(),
            "alpha": alpha,
            "n_items": int(m.group("n")),
            "threshold_met": alpha >= 0.7,
        })
    flagged = [r["construct"] for r in rows if not r["threshold_met"]]
    interp = (
        "All scales meet the α ≥ 0.7 threshold (Nunnally, 1978)."
        if all_meet
        else f"α below 0.7 for: {', '.join(flagged)}. Consider dropping weak items or reformulating."
    )
    return {
        "step_name": "Reliability (Cronbach's Alpha)",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


# Regression coefficient table — predictor name + (B, Std.Error, Standardized Beta?, t, Sig.).
_REGRESSION_ROW = re.compile(
    r"^(?P<predictor>\w[\w\s]*?)\s+"
    r"(?P<b>-?\d+\.\d+|\.\d+)\s+"            # Unstandardized B
    r"(?P<se>-?\d+\.\d+|\.\d+)\s+"           # Std. Error
    r"(?P<beta>-?\d+\.\d+|\.\d+)?\s*"        # Standardized Beta (absent for constant)
    r"(?P<t>-?\d+\.\d+)\s+"                  # t
    r"(?P<sig>\.\d+|\d+\.\d+)\s*$",          # Sig.
    re.MULTILINE,
)
_RSQ = re.compile(r"R\s+R\s*Square[^\n]*\n([\d.]+)\s+([\d.]+)\s+([\d.]+)", re.IGNORECASE)
_VIF_ROW = re.compile(
    r"^(?P<predictor>\w[\w\s]*?)\s+(?P<tol>\.\d+|\d+\.\d+)\s+(?P<vif>\d+\.\d+)\s*$",
    re.MULTILINE,
)


def _extract_regression(text: str) -> dict | None:
    coefs = list(_REGRESSION_ROW.finditer(text))
    if not coefs:
        return None
    rows = []
    for m in coefs:
        predictor = m.group("predictor").strip()
        if predictor.lower() in ("model", "(constant)"):
            # Keep the constant but tag it
            rows.append({
                "predictor": "(Constant)",
                "B": float(m.group("b")),
                "beta": None,
                "t": float(m.group("t")),
                "sig": float(m.group("sig")),
                "significant": float(m.group("sig")) < 0.05,
            })
            continue
        rows.append({
            "predictor": predictor,
            "B": float(m.group("b")),
            "beta": float(m.group("beta")) if m.group("beta") else None,
            "t": float(m.group("t")),
            "sig": float(m.group("sig")),
            "significant": float(m.group("sig")) < 0.05,
        })

    # R², adjusted R²
    rsq_match = _RSQ.search(text)
    r2 = float(rsq_match.group(2)) if rsq_match else None

    # VIF table — augment predictor rows with VIF
    vif_map = {m.group("predictor").strip(): float(m.group("vif"))
               for m in _VIF_ROW.finditer(text)}
    for row in rows:
        if row["predictor"] in vif_map:
            row["VIF"] = vif_map[row["predictor"]]

    significant = [r["predictor"] for r in rows
                   if r["predictor"] != "(Constant)" and r["significant"]]
    interp_parts = []
    if significant:
        interp_parts.append(
            f"Significant predictors: {', '.join(significant)} (p < 0.05)."
        )
    if r2 is not None:
        interp_parts.append(f"R² = {r2:.3f}.")
    high_vif = [r["predictor"] for r in rows if r.get("VIF", 0) > 10]
    if high_vif:
        interp_parts.append(f"Multicollinearity (VIF > 10) for: {', '.join(high_vif)}.")
    interp = " ".join(interp_parts) or "Regression results extracted."

    return {
        "step_name": "Regression Analysis",
        "table": rows,
        "thresholds_met": not high_vif,
        "interpretation": interp,
        "parser": "regex",
    }


# Dispatch — each step name maps to its extractor function.
_SPSS_EXTRACTORS = {
    "Reliability (Cronbach's Alpha)": _extract_cronbach,
    "Regression Analysis": _extract_regression,
    # EFA, Correlation, ANOVA extractors land in a follow-up; LLM fallback
    # handles them today.
}


def parse_spss(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _SPSS_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
