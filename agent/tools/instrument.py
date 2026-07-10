"""Questionnaire Doctor — deterministic instrument lint before fielding.

Advisory (Global Constraint): returns findings + a scale-provenance skeleton;
NEVER blocks the student from fielding. This is item-writing *guidance*, not
psychometric computation — there is no data yet, so nothing here computes
Cronbach's alpha or loadings; it catches the item-wording and coverage mistakes
that quietly wreck a dataset before a single response is collected.

Decision: the lint logic lives in a plain function (`audit_instrument_findings`)
so BOTH the LangChain @tool (agent surface) and the F3 rubric criterion
(quality/rubric.py) can call the exact same rules — the two can never disagree
about what "a good questionnaire" means. Same pure-core / thin-tool split F8's
preflight uses.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

# Coordinating conjunctions (EN + VI) that usually mean an item bundles two
# ideas into one question ("fast AND reliable") — a double-barreled item the
# respondent can't answer cleanly. VI included because the default market is
# Vietnamese (project_sibling_products memory).
_CONJ = (" and ", " or ", " và ", " hoặc ")


def audit_instrument_findings(instrument: dict, hypotheses: list, constructs: list) -> dict:
    """Pure lint core. Returns {"findings": [...], "scale_provenance": [...]}.

    Findings are all "soft" — advisory. Shared by the @tool below and the
    rubric's instrument_quality dimension.
    """
    items = (instrument or {}).get("items") or []
    findings: list[dict] = []

    # 1) Double-barreled items — a conjunction joining two ideas.
    for it in items:
        text = (it.get("text") or "").lower()
        if any(c in text for c in _CONJ):
            findings.append({
                "issue": f"Item {it.get('id')} may be double-barreled (joins two ideas): "
                         f"'{it.get('text')}'",
                "fix": "Split into two separate items.", "severity": "soft"})

    # 2) Reverse-coded coverage per construct — zero reverse items on a construct
    #    means careless-responding can't be caught for it.
    by_construct: dict = {}
    for it in items:
        by_construct.setdefault(it.get("construct"), []).append(it)
    for c in (constructs or []):
        group = by_construct.get(c, [])
        if group and not any(i.get("reverse_coded") for i in group):
            findings.append({
                "issue": f"Construct '{c}' has no reverse-coded item.",
                "fix": "Add one reverse-coded item to catch careless responding.",
                "severity": "soft"})

    # 3) At least one attention check across the whole instrument.
    if items and not any(it.get("attention_check") for it in items):
        findings.append({
            "issue": "No attention-check item.",
            "fix": "Add at least one attention check.", "severity": "soft"})

    # Scale-provenance skeleton — one row per construct for the student to fill
    # (where the scale came from, what it was adapted from, whether it was
    # back-translated). An empty provenance table is itself the reminder.
    provenance = [{"construct": c, "source": "", "adapted_from": "", "back_translated": False}
                  for c in (constructs or [])]
    return {"findings": findings, "scale_provenance": provenance}


@tool
def audit_instrument(instrument: dict, hypotheses: list, constructs: list) -> str:
    """Lint a questionnaire before fielding.

    Checks for double-barreled/leading items, reverse-coded coverage per
    construct, and attention checks, and returns a scale-provenance skeleton to
    fill in (where each scale came from / what it was adapted from). Advisory —
    surface the findings and offer fixes; never refuse to field.

    Args:
        instrument: {"items": [{"id", "text", "construct", "reverse_coded",
                     "attention_check"}, ...]}.
        hypotheses: the study's hypotheses (reserved for future cross-checks).
        constructs: construct names to check reverse-coded coverage for.
    """
    return json.dumps(audit_instrument_findings(instrument, hypotheses, constructs),
                      ensure_ascii=False)
