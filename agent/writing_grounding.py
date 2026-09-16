"""Conservative state grounding for generated M5 prose.

This module deliberately has no dependency on ``agent.coherence`` or M5 tools:
both call paths need it and importing either would create a validation cycle.
It reports only explicit, checkable conflicts. Broader semantic judgement belongs
to the review rubric, where an LLM can inspect the full chapter and evidence.
"""
from __future__ import annotations

import re
import unicodedata
from math import isfinite
from typing import Any


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or "")).casefold()).strip()


def _chapters(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item.get("prose") if isinstance(item, dict) else item)
                for key, item in value.items() if isinstance(item, (str, dict))}
    if isinstance(value, list):
        return {str(item.get("chapter_name") or item.get("name") or item.get("title") or "section"):
                str(item.get("prose") or item.get("body") or "")
                for item in value if isinstance(item, dict)}
    return {}


def _canonical_results(flat_context: dict) -> Any:
    m4 = flat_context.get("m4_analysis") if isinstance(flat_context.get("m4_analysis"), dict) else {}
    canonical = flat_context.get("analysis_results", m4.get("analysis_results"))
    if canonical not in (None, "", {}, []):
        return canonical
    return flat_context.get("results", m4.get("results"))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _contains_metric(value: Any, names: set[str]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if _norm(key).replace("_", "") in names and _number(child):
                return True
            if _contains_metric(child, names):
                return True
    elif isinstance(value, list):
        return any(_contains_metric(child, names) for child in value)
    return False


def _has_numeric(value: Any) -> bool:
    if _number(value):
        return True
    if isinstance(value, dict):
        return any(_has_numeric(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_numeric(child) for child in value)
    return False


def _diagnostic_evidence(results: Any, diagnostic: str) -> bool:
    if not isinstance(results, dict):
        return False
    if diagnostic == "rho_a":
        return _contains_metric(results.get("measurement_model"), {"rhoa"})
    if diagnostic == "htmt":
        dv = results.get("discriminant_validity")
        if not isinstance(dv, dict):
            return False
        if _number(dv.get("htmt")) or _has_numeric(dv.get("htmt")):
            return True
        return (_norm(dv.get("method")) == "htmt" and
                _has_numeric(dv.get("matrix")))
    if diagnostic == "loadings":
        return (_contains_metric(results.get("measurement_model"), {"loading", "outerloading"}) or
                _contains_metric(results.get("outer_loadings"), {"loading", "outerloading", "value"}))
    if diagnostic == "reliability":
        return _contains_metric(results.get("measurement_model"), {"cronbachalpha", "alpha", "compositereliability", "cr", "rhoa"})
    if diagnostic == "validity":
        return (_contains_metric(results.get("measurement_model"), {"ave"}) or
                _diagnostic_evidence(results, "htmt"))
    return False


_NEGATED = re.compile(r"\b(?:not|no|without|unavailable|pending|missing|không|chưa|thiếu)\b", re.I)
_PASS = re.compile(
    r"\b(?:pass(?:ed)?|meet(?:s|ing)?|exceed(?:s|ed)?|above|below|acceptable|satisfactory|"
    r"valid|reliable|đạt|vượt|dưới|thỏa|phù hợp|chấp nhận)\b", re.I)
_THEORETICAL_THRESHOLD = re.compile(
    r"(?:\bhtmt\b|giá trị phân biệt)\s+(?:threshold|ngưỡng|criterion|tiêu chuẩn)\s*(?:is|=|là)|"
    r"(?:\bhtmt\b|giá trị phân biệt)\s+(?:below|dưới)\s*\d[\d.,]*\s+"
    r"(?:indicates|means|cho thấy|biểu thị)", re.I)
_GENERAL_CRITERION = re.compile(
    r"\b(?:are|is)\s+considered\b|\b(?:criterion|threshold|standard)\b|"
    r"được\s+(?:đánh giá|chấp nhận)|tiêu chuẩn|ngưỡng", re.I)
_EMPIRICAL_SUBJECT = re.compile(
    r"\b(?:results?|our|observed|model|constructs?|all)\b|"
    r"kết quả|các\s+giá trị|mô hình|đều|quan sát", re.I)
_DIAGNOSTICS = {
    "rho_a": re.compile(r"\brho[_\s-]?a\b", re.I),
    "htmt": re.compile(r"\bhtmt\b", re.I),
    "loadings": re.compile(r"\b(?:outer\s+)?loadings?\b|hệ số tải", re.I),
    "reliability": re.compile(r"\b(?:internal\s+)?reliability\b|độ tin cậy", re.I),
    "validity": re.compile(r"\b(?:discriminant|convergent)\s+validity\b|giá trị phân biệt|giá trị hội tụ", re.I),
}


def _finding(check: str, message: str, *, chapter: str, sentence: str,
             observed: Any = None, expected: Any = None, construct: str | None = None) -> dict:
    return {
        "check": check, "severity": "soft", "message": message,
        "location": {"table": None, "construct": construct, "item": None, "path": None,
                     "hypothesis": None, "chapter": chapter, "sentence": sentence},
        "observed": observed, "expected": expected, "tolerance": None, "source": "state",
    }


def _sentences(prose: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", prose) if part.strip()]


def _construct_labels(flat_context: dict) -> dict[str, str]:
    m3 = flat_context.get("m3_design") if isinstance(flat_context.get("m3_design"), dict) else {}
    constructs = flat_context.get("constructs", m3.get("constructs")) or []
    cm = flat_context.get("conceptual_model", m3.get("conceptual_model")) or {}
    # Match the composition register: explicit M3 construct definitions take
    # precedence over an older diagram's display labels.
    rows = list(cm.get("nodes") or []) if isinstance(cm, dict) else []
    if isinstance(constructs, list):
        rows.extend(constructs)
    labels = {}
    for row in rows:
        if isinstance(row, dict):
            code = str(row.get("id") or row.get("code") or "").strip()
            label = str(row.get("label") or row.get("name") or "").strip()
            if code and label:
                labels[code] = label
    return labels


def _alias_findings(chapter: str, sentence: str, labels: dict[str, str]) -> list[dict]:
    findings = []
    # Exact explicit declarations only: ATT = <known EXP label>, or ATT
    # (known EXP label). Do not infer drift from ordinary prose or paths.
    for code, expected in labels.items():
        pattern = re.compile(rf"\b{re.escape(code)}\b\s*(?:=|:|\(|là|is)\s*([^;,.\)]+)", re.I)
        for match in pattern.finditer(sentence):
            observed = match.group(1).strip()
            owner = next((other for other, label in labels.items()
                          if other != code and _norm(label) == _norm(observed)), None)
            if owner:
                findings.append(_finding(
                    "grounding.construct_alias_conflict",
                    f"{code} is explicitly labelled as {observed!r}, but that is the canonical label for {owner}.",
                    chapter=chapter, sentence=sentence, construct=code,
                    observed=observed, expected=expected,
                ))
    return findings


def grounding_findings(chapters: Any, flat_context: dict) -> list[dict]:
    """Return soft, actionable evidence conflicts for M5 prose.

    A finding requires an explicit diagnostic *pass* claim with no matching
    canonical metric, or an exact declaration that assigns one construct's
    canonical label to another. Threshold descriptions, negations, and prose
    saying a metric was not reported remain unflagged by design.
    """
    context = flat_context if isinstance(flat_context, dict) else {}
    results = _canonical_results(context)
    labels = _construct_labels(context)
    findings: list[dict] = []
    for chapter, prose in _chapters(chapters).items():
        for sentence in _sentences(prose):
            findings.extend(_alias_findings(chapter, sentence, labels))
            if (_NEGATED.search(sentence) or not _PASS.search(sentence) or
                    _THEORETICAL_THRESHOLD.search(sentence) or
                    (_GENERAL_CRITERION.search(sentence) and not _EMPIRICAL_SUBJECT.search(sentence))):
                continue
            for name, pattern in _DIAGNOSTICS.items():
                if pattern.search(sentence) and not _diagnostic_evidence(results, name):
                    findings.append(_finding(
                        "coherence.unsupported_diagnostic_claim",
                        f"The prose says {name.replace('_', ' ')} passed, but canonical analysis_results has no matching metric.",
                        chapter=chapter, sentence=sentence,
                        observed={"metric": name, "sentence": sentence},
                        expected="canonical analysis_results metric",
                    ))
    return findings
