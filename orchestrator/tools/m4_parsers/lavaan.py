"""R lavaan paste-text parser — CFA + structural model fit indices."""
from __future__ import annotations

import re


_FIT_INDEX_PATTERNS = {
    "CFI":   r"Comparative Fit Index \(CFI\)\s+(\d+\.\d+)",
    "TLI":   r"Tucker-Lewis Index \(TLI\)\s+(\d+\.\d+)",
    "RMSEA": r"RMSEA\s+(\d+\.\d+)",
    "SRMR":  r"SRMR\s+(\d+\.\d+)",
}


def _extract_cfa(text: str) -> dict | None:
    rows = []
    for index_name, pattern in _FIT_INDEX_PATTERNS.items():
        m = re.search(pattern, text)
        if not m:
            continue
        value = float(m.group(1))
        # Standard thresholds: CFI/TLI ≥ 0.90; RMSEA ≤ 0.08; SRMR ≤ 0.08
        if index_name in ("CFI", "TLI"):
            met = value >= 0.90
        else:
            met = value <= 0.08
        rows.append({
            "index": index_name,
            "value": value,
            "threshold_met": met,
        })
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [r["index"] for r in rows if not r["threshold_met"]]
    interp = (
        "Model fit meets Hu & Bentler (1999) standards (CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08)."
        if all_meet
        else f"⚠️ Fit indices below threshold: {', '.join(failed)}. Consider model respecification."
    )
    return {
        "step_name": "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_LAVAAN_EXTRACTORS = {
    "Confirmatory Factor Analysis (CFI/TLI/RMSEA)": _extract_cfa,
    # Structural Model, Mediation, etc. — extend in follow-ups.
}


def parse_lavaan(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _LAVAAN_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
