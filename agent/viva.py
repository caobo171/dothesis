"""Rubric-grounded viva (defense) simulation — PURE, deterministic, offline.

Turns the thesis's ACTUAL weaknesses — every material `score_thesis` finding
plus three state-direct signals the rubric doesn't join — into targeted
committee questions with grounded model-answer hints and per-question grading
criteria, ranked by defensibility (must-fix vs disclosable).

Zero LLM calls: findings, targeting, difficulty, hints, criteria, readiness are
all deterministic. The only LLM touchpoints stay OUTSIDE this module — the
rubric's judge dims (best-effort, upstream) and the skill's drill voice.

Never fabricates: every non-staple question's `grounding` carries the finding's
verbatim `issue` (rubric) or state-read `values` (signals). `generate_viva`
never raises — junk state degrades to the four staples.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_JUDGE_PLACEHOLDER = "could not evaluate"     # quality/rubric.py judge-failure stub
_PER_DIM_CAP = 3
_TOTAL_CAP = 30

# Dimensions whose findings become questions, with their question/hint templates.
# `hint` reuses the finding's own `fix` (the per-check fix text already written
# in each dimension) behind a defensibility framing.
_DIM_TEMPLATES: Dict[str, dict] = {
    "coherence": {
        "category": "coherence",
        "q": "Your text and your results table disagree: {issue} Which is correct?",
        "hint": "MUST FIX before the defense: {fix} A number mismatch cannot be defended — "
                "reconcile prose and results, then re-drill.",
        "criteria": ["Identifies which figure is correct and why",
                     "Explains how the mismatch arose",
                     "Commits to reconciling prose and results table"]},
    "stats_validity": {
        "category": "stats_validity",
        "q": "{issue} Can you walk the committee through how this value was computed?",
        "hint": "MUST FIX: {fix} An examiner recomputing this will find it — correct the source, "
                "never the narration.",
        "criteria": ["Names the statistic and how it was computed",
                     "Shows the value is internally consistent",
                     "Does not defend a provably-wrong number"]},
    "citations": {
        "category": "citations",
        "q": "{issue} Where can the committee find this source?",
        "hint": "MUST FIX: {fix}",
        "criteria": ["Produces the full reference",
                     "Confirms it exists in the reference list",
                     "Does not defend an unverifiable citation"]},
    "advisor": {
        "category": "advisor",
        "q": "Your advisor required: {issue} — show the committee where you addressed it.",
        "hint": "MUST FIX: {fix} Committees include the advisor.",
        "criteria": ["Points to where the requirement was addressed",
                     "Explains the change made",
                     "Does not dismiss the advisor directive"]},
    "similarity": {
        "category": "similarity",
        "q": "{issue} How do you respond to a similarity query on this passage?",
        "hint": "Disclose and fix hygiene: {fix}",
        "criteria": ["Explains the overlap (quote, common phrasing, or paraphrase)",
                     "Commits to quotation/citation hygiene",
                     "Distinguishes a self-check from Turnitin"]},
    "source_verification": {
        "category": "source_verification",
        "q": "{issue} How did you verify this source?",
        "hint": "Disclose: {fix} Verify before the defense if possible.",
        "criteria": ["Describes how the source was verified",
                     "Acknowledges any unverified DOIs",
                     "Commits to verifying before the defense"]},
    "preflight": {
        "category": "preflight",
        "q": "{issue} — how do you justify this design choice to the committee?",
        "hint": "Disclose and frame: {fix}",
        "criteria": ["Justifies the design choice", "Acknowledges the trade-off"]},
    "instrument_quality": {
        "category": "instrument_quality",
        "q": "{issue} — how do you justify this design choice to the committee?",
        "hint": "Disclose and frame: {fix}",
        "criteria": ["Justifies the instrument design", "Acknowledges the limitation"]},
    "results_validity": {
        "category": "results_validity",
        "q": "{issue} — how do you justify this design choice to the committee?",
        "hint": "Disclose and frame: {fix}",
        "criteria": ["Justifies the result", "Acknowledges the limitation"]},
    "structure": {
        "category": "structure",
        "q": "{issue} — how do you justify this to the committee?",
        "hint": "Disclose and frame: {fix}",
        "criteria": ["Explains the structural choice", "Commits to fixing gaps"]},
    "no_stubs": {
        "category": "structure",
        "q": "{issue} — the committee will see this. What is your plan?",
        "hint": "MUST FIX: {fix}",
        "criteria": ["Acknowledges the placeholder", "Commits to composing real content"]},
}


def _severity_to_difficulty(sev: str) -> str:
    return "hard" if sev == "hard" else "medium"


def _severity_to_defensibility(sev: str) -> str:
    return "must_fix" if sev == "hard" else "disclosable"


def _fmt(tpl: str, **kw) -> str:
    try:
        return tpl.format(**kw)
    except Exception:
        return tpl


def rubric_questions(rubric_result: Optional[dict]) -> List[dict]:
    """One question per material rubric finding, capped per dimension and deduped.
    Judge-failure placeholders are skipped (never invented weaknesses)."""
    if not isinstance(rubric_result, dict):
        return []
    out: List[dict] = []
    for dim in rubric_result.get("dimensions") or []:
        if not isinstance(dim, dict):
            continue
        name = dim.get("name", "general")
        tpl = _DIM_TEMPLATES.get(name)
        findings = [f for f in (dim.get("findings") or []) if isinstance(f, dict)]
        # hard findings first so the per-dimension cap keeps the worst ones
        findings.sort(key=lambda f: 0 if f.get("severity") == "hard" else 1)
        seen = set()
        kept = 0
        for f in findings:
            issue = f.get("issue")
            if not issue or _JUDGE_PLACEHOLDER in str(issue).lower():
                continue
            key = (name, issue)
            if key in seen:
                continue
            seen.add(key)
            if kept >= _PER_DIM_CAP:
                continue
            kept += 1
            sev = f.get("severity", "soft")
            fix = f.get("fix", "Acknowledge and defend, or disclose as a limitation.")
            if tpl:
                q_text = _fmt(tpl["q"], issue=issue, fix=fix)
                hint = _fmt(tpl["hint"], issue=issue, fix=fix)
                category = tpl["category"]
                criteria = list(tpl["criteria"])
            else:  # unknown dimension → today's generic phrasing (parity, not a drop)
                q_text = f"A weakness was flagged: {issue}. How do you respond?"
                hint = fix
                category = name
                criteria = ["Acknowledges the weakness", "Defends or discloses it"]
            out.append({
                "category": category, "question": q_text,
                "targets": name, "difficulty": _severity_to_difficulty(sev),
                "defensibility": _severity_to_defensibility(sev),
                "model_answer_hint": hint, "answer_criteria": criteria,
                "grounding": {"source": f"rubric:{name}", "severity": sev, "issue": issue,
                              "chapter": f.get("chapter"), "values": None}})
    return out


# --- state-direct signals the rubric doesn't join ---------------------------

def _achieved_n(m4: dict) -> Optional[int]:
    ar = m4.get("analysis_results")
    if isinstance(ar, dict):
        n = (ar.get("descriptives") or {}).get("n")
        if isinstance(n, (int, float)):
            return int(n)
    resp = m4.get("field_it_responses")
    if isinstance(resp, list) and resp:
        return len(resp)
    return None


def _staples(cs: dict) -> List[dict]:
    m1 = cs.get("m1_topic") if isinstance(cs.get("m1_topic"), dict) else {}
    pop = m1.get("target_population") or m1.get("scope")
    gen_q = (f"How far do your findings generalize beyond {pop}?" if pop
             else "How far do your findings generalize beyond your sample?")

    def s(cat, q, targets, crit):
        return {"category": cat, "question": q, "targets": targets, "difficulty": "medium",
                "defensibility": "standard", "model_answer_hint": "", "answer_criteria": crit,
                "grounding": {"source": "staple", "severity": None, "issue": None,
                              "chapter": None, "values": None}}
    return [
        s("contribution", "What is the single most important contribution of your study?",
          "contribution", ["States one theoretical and one practical contribution"]),
        s("methodology", "Why did you choose this analysis method over the alternatives?",
          "method choice", ["Ties the choice to model type, sample size, and construct nature"]),
        s("limitations", "What are the main limitations of your study?",
          "limitations", ["Names 2–3 honest limitations with mitigation or future work"]),
        s("generalizability", gen_q, "generalizability",
          ["States the population and scope boundary", "Avoids over-claiming"]),
    ]


def state_signal_questions(cs: dict) -> List[dict]:
    """Power shortfall, not-supported hypotheses, field-quality flags — the
    numbers the rubric doesn't join. Plus the four always-on staples."""
    m3 = cs.get("m3_design") if isinstance(cs.get("m3_design"), dict) else {}
    m4 = cs.get("m4_analysis") if isinstance(cs.get("m4_analysis"), dict) else {}
    out: List[dict] = []

    # --- power / sample size (mutually exclusive: real a-priori N beats legacy) --
    sp = m3.get("sample_plan") if isinstance(m3.get("sample_plan"), dict) else {}
    pa = sp.get("power_analysis") if isinstance(sp.get("power_analysis"), dict) else {}
    required = pa.get("recommended_n") or pa.get("required_n")
    achieved = _achieved_n(m4)
    if isinstance(required, (int, float)) and isinstance(achieved, (int, float)):
        required = int(required)
        shortfall = (required - achieved) / required if required else 0
        if achieved < required:
            just = str(pa.get("justification") or "")
            diff = "hard" if shortfall >= 0.20 else "medium"
            out.append({
                "category": "methodology",
                "question": f"You collected n={achieved} but your own a-priori analysis requires "
                            f"N={required}. Justify your statistical power.",
                "targets": "statistical power", "difficulty": diff, "defensibility": "disclosable",
                "model_answer_hint": (f"Disclose and frame: acknowledge n={achieved} < N={required}; "
                                      f"cite the a-priori method from your plan"
                                      + (f" ({just})" if just else "")
                                      + "; frame as a boundary condition with a post-hoc achieved-power "
                                        "figure and a future-work note — not a fatal flaw, never an excuse."),
                "answer_criteria": ["States the achieved n and required N explicitly",
                                    "Cites the a-priori method used in the plan",
                                    "Frames the shortfall as a boundary condition with future work",
                                    "Does not blame the data or the committee's threshold"],
                "grounding": {"source": "state:power", "severity": "soft", "issue": None,
                              "chapter": "methodology",
                              "values": {"n_achieved": achieved, "required_n": required}}})
    else:
        # legacy small-n heuristic (no a-priori power analysis available)
        target_n = sp.get("target_n")
        if isinstance(target_n, (int, float)) and target_n < 200:
            out.append({
                "category": "methodology",
                "question": f"Your sample size is {int(target_n)}. How do you justify statistical "
                            "power and generalizability?",
                "targets": "sample size", "difficulty": "medium", "defensibility": "disclosable",
                "model_answer_hint": "Cite the 10× / inverse-sqrt rule and acknowledge it as a "
                                     "limitation with a future-work note.",
                "answer_criteria": ["Cites a sample-size rule", "Acknowledges it as a limitation"],
                "grounding": {"source": "state:sample_size", "severity": "soft", "issue": None,
                              "chapter": "methodology", "values": {"target_n": int(target_n)}}})

    # --- not-supported hypotheses --------------------------------------------
    ar = m4.get("analysis_results")
    if isinstance(ar, dict):
        kept = 0
        for ht in (ar.get("hypothesis_tests") or []):
            if not isinstance(ht, dict):
                continue
            decision = str(ht.get("decision") or "").lower()
            if decision and not decision.startswith("support"):
                if kept >= _PER_DIM_CAP:
                    break
                kept += 1
                hid = ht.get("id") or ht.get("hypothesis") or "A hypothesis"
                path = ht.get("path") or ""
                nums = ht.get("numbers") or {}
                beta, p = nums.get("beta"), nums.get("p")
                detail = f" (β={beta}, p={p})" if beta is not None or p is not None else ""
                out.append({
                    "category": "results",
                    "question": f"{hid} ({path}){detail} was not supported. Why, and what does "
                                "that mean theoretically?",
                    "targets": "rejected hypothesis", "difficulty": "hard",
                    "defensibility": "disclosable",
                    "model_answer_hint": "Offer a theoretical/contextual explanation tied to your "
                                         "model — a null result is a finding, not a failure; never a "
                                         "data-quality excuse.",
                    "answer_criteria": ["Gives a theoretical/contextual reason",
                                        "Frames the null as a legitimate finding",
                                        "Avoids a data-quality excuse"],
                    "grounding": {"source": "state:hypothesis", "severity": "soft",
                                  "issue": None, "chapter": "results",
                                  "values": {"id": str(hid), "decision": decision}}})
    elif isinstance(ar, str):
        low = ar.lower()
        if "not support" in low or "reject" in low or "p=0.2" in low:
            out.append({
                "category": "results",
                "question": "One of your hypotheses was not supported. Why do you think that is, "
                            "and what does it mean theoretically?",
                "targets": "rejected hypothesis", "difficulty": "hard", "defensibility": "disclosable",
                "model_answer_hint": "Offer a theoretical/contextual explanation, not a data-quality "
                                     "excuse.",
                "answer_criteria": ["Gives a theoretical reason", "Avoids a data-quality excuse"],
                "grounding": {"source": "state:hypothesis", "severity": "soft", "issue": None,
                              "chapter": "results", "values": None}})

    # --- field/instrument data-quality flags ---------------------------------
    fq = m4.get("field_it_quality")
    if isinstance(fq, list) and fq:
        out.append({
            "category": "data_quality",
            "question": f"Your data-quality screening flagged {len(fq)} issue(s). How did you "
                        "handle them?",
            "targets": "data quality", "difficulty": "medium", "defensibility": "disclosable",
            "model_answer_hint": "Describe the screening (careless responses, outliers, missingness) "
                                 "and the defensible handling you applied.",
            "answer_criteria": ["Describes the screening applied", "Justifies the handling choice"],
            "grounding": {"source": "state:data_quality", "severity": "soft", "issue": None,
                          "chapter": "methodology", "values": {"flag_count": len(fq)}}})

    out += _staples(cs)
    return out


# --- envelope assembly ------------------------------------------------------

_ORDER = {"must_fix": 0, "disclosable": 1, "standard": 2}


def readiness(questions: List[dict], rubric_result: Optional[dict] = None) -> dict:
    must_fix = sum(1 for q in questions if q.get("defensibility") == "must_fix")
    disclosable = sum(1 for q in questions if q.get("defensibility") == "disclosable")
    by_dim: Dict[str, int] = {}
    if isinstance(rubric_result, dict):
        for dim in rubric_result.get("dimensions") or []:
            if isinstance(dim, dict):
                fs = [f for f in (dim.get("findings") or [])
                      if isinstance(f, dict) and f.get("issue")
                      and _JUDGE_PLACEHOLDER not in str(f.get("issue")).lower()]
                if fs:
                    by_dim[dim.get("name", "general")] = len(fs)
    if must_fix:
        verdict = "not_ready"
    elif disclosable:
        verdict = "ready_with_disclosures"
    else:
        verdict = "ready"
    summary = (f"{must_fix} must-fix finding(s) block a confident defense; "
               f"{disclosable} weakness(es) are disclosable." if must_fix
               else (f"No blocking findings; {disclosable} weakness(es) to disclose."
                     if disclosable else "No material weaknesses — the classic questions only."))
    return {"verdict": verdict, "must_fix": must_fix, "disclosable": disclosable,
            "by_dimension": by_dim, "summary": summary}


def generate_viva(cs: Optional[dict], rubric_result: Optional[dict] = None) -> dict:
    """Full deterministic viva envelope. Never raises — junk state degrades to
    the four staples with verdict 'ready'."""
    try:
        cs = cs if isinstance(cs, dict) else {}
        rubric_ok = isinstance(rubric_result, dict) and isinstance(
            rubric_result.get("dimensions"), list)
        questions = rubric_questions(rubric_result if rubric_ok else None)
        questions += state_signal_questions(cs)
        # dedup on (category, issue-or-question), stable order
        seen = set()
        deduped = []
        for q in questions:
            key = (q.get("category"), (q.get("grounding") or {}).get("issue") or q.get("question"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(q)
        deduped.sort(key=lambda q: _ORDER.get(q.get("defensibility"), 3))
        deduped = deduped[:_TOTAL_CAP]
        for i, q in enumerate(deduped, 1):
            q["id"] = f"q-{q.get('category', 'gen')}-{i}"
        method = rubric_result.get("method") if rubric_ok else None
        return {"questions": deduped,
                "readiness": readiness(deduped, rubric_result if rubric_ok else None),
                "meta": {"generator": "viva-v2-deterministic",
                         "rubric_available": bool(rubric_ok), "method": method}}
    except Exception:
        staples = _staples(cs if isinstance(cs, dict) else {})
        for i, q in enumerate(staples, 1):
            q["id"] = f"q-{q['category']}-{i}"
        return {"questions": staples, "readiness": readiness(staples),
                "meta": {"generator": "viva-v2-deterministic", "rubric_available": False,
                         "method": None}}
