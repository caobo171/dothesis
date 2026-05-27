"""SmartPLS report paste-text parser."""
from __future__ import annotations

import re


def _extract_outer_loadings(text: str) -> dict | None:
    """Outer Loadings table — item rows with one numeric column per construct."""
    if "Outer Loadings" not in text:
        return None
    block_match = re.search(
        r"Outer Loadings\s*\n\s*((?:[A-Za-z][\w]*\s*)+)\n((?:.+\n?)+?)(?=\n\s*\n|Construct Reliability|\Z)",
        text,
    )
    if not block_match:
        return None
    header = block_match.group(1).split()
    body = block_match.group(2)
    rows = []
    for line in body.splitlines():
        parts = line.split()
        if not parts:
            continue
        item = parts[0]
        # Find the single numeric value in the row; map it to the construct
        # under whose column the value appears.
        for i, p in enumerate(parts[1:]):
            try:
                loading = float(p)
            except ValueError:
                continue
            construct = header[i] if i < len(header) else "?"
            rows.append({
                "item": item,
                "construct": construct,
                "loading": loading,
                "threshold_met": loading >= 0.7,
            })
            break
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [r["item"] for r in rows if not r["threshold_met"]]
    interp = (
        "All outer loadings >= 0.7 (Hair et al., 2019)."
        if all_meet
        else f"Items below 0.7: {', '.join(failed)}. Consider dropping these from the construct."
    )
    return {
        "step_name": "Outer Loadings",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_AVE_ROW = re.compile(
    r"^(?P<construct>\w[\w]*?)\s+(?P<alpha>\d+\.\d+)\s+(?P<cr>\d+\.\d+)\s+(?P<ave>\d+\.\d+)\s*$",
    re.MULTILINE,
)


def _extract_ave_cr(text: str) -> dict | None:
    matches = list(_AVE_ROW.finditer(text))
    if not matches:
        return None
    rows = []
    all_meet = True
    for m in matches:
        ave = float(m.group("ave"))
        cr = float(m.group("cr"))
        alpha = float(m.group("alpha"))
        meets = ave >= 0.5 and cr >= 0.7 and alpha >= 0.7
        if not meets:
            all_meet = False
        rows.append({
            "construct": m.group("construct"),
            "alpha": alpha, "CR": cr, "AVE": ave,
            "threshold_met": meets,
        })
    failed = [r["construct"] for r in rows if not r["threshold_met"]]
    interp = (
        "Convergent validity established (AVE >= 0.5, CR >= 0.7, alpha >= 0.7)."
        if all_meet
        else f"Convergent validity issues for: {', '.join(failed)}."
    )
    return {
        "step_name": "Convergent Validity: AVE & CR",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_PATH_ROW = re.compile(
    r"^(?P<src>\w[\w]*?)\s+->\s+(?P<dst>\w[\w]*?)\s+"
    r"(?P<beta>-?\d+\.\d+)\s+(?P<t>\d+\.\d+)\s+(?P<p>\d+\.\d+)\s*$",
    re.MULTILINE,
)


def _extract_path_coefficients(text: str) -> dict | None:
    matches = list(_PATH_ROW.finditer(text))
    if not matches:
        return None
    rows = []
    for m in matches:
        p = float(m.group("p"))
        rows.append({
            "path": f"{m.group('src')} -> {m.group('dst')}",
            "beta": float(m.group("beta")),
            "t": float(m.group("t")),
            "p": p,
            "significant": p < 0.05,
        })
    significant = [r["path"] for r in rows if r["significant"]]
    all_significant = all(r["significant"] for r in rows)
    interp = (
        f"All {len(rows)} hypothesized paths are significant (p < 0.05)."
        if all_significant
        else f"Significant paths: {', '.join(significant) if significant else 'none'}."
    )
    return {
        "step_name": "Path Coefficients (Bootstrap 5000)",
        "table": rows,
        "thresholds_met": all_significant,
        "interpretation": interp,
        "parser": "regex",
    }


def _extract_htmt(text: str) -> dict | None:
    """HTMT matrix — extract pairwise ratios; flag any > 0.85."""
    block = re.search(
        r"Heterotrait-Monotrait Ratio \(HTMT\)\s*\n((?:.+\n?)+?)(?=\n\s*\n|\Z)",
        text,
    )
    if not block:
        return None
    body = block.group(1)
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return None
    # First non-empty line is the header row with construct names.
    header = lines[0].split()
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        construct_a = parts[0]
        for i, p in enumerate(parts[1:]):
            try:
                htmt = float(p)
            except ValueError:
                continue
            construct_b = header[i] if i < len(header) else "?"
            if construct_a != construct_b:
                rows.append({
                    "construct_a": construct_a,
                    "construct_b": construct_b,
                    "htmt": htmt,
                    "threshold_met": htmt < 0.85,
                })
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [f"{r['construct_a']}-{r['construct_b']}" for r in rows if not r["threshold_met"]]
    interp = (
        "Discriminant validity established (HTMT < 0.85; Henseler et al., 2015)."
        if all_meet
        else f"HTMT >= 0.85 for: {', '.join(failed)}. Constructs may overlap."
    )
    return {
        "step_name": "Discriminant Validity: HTMT & Fornell-Larcker",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_SMARTPLS_EXTRACTORS = {
    "Outer Loadings": _extract_outer_loadings,
    "Convergent Validity: AVE & CR": _extract_ave_cr,
    "Path Coefficients (Bootstrap 5000)": _extract_path_coefficients,
    "Discriminant Validity: HTMT & Fornell-Larcker": _extract_htmt,
    # VIF, R^2, f^2, Q^2, mediation extractors land in a follow-up; LLM fallback
    # handles them today.
}


def parse_smartpls(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _SMARTPLS_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
