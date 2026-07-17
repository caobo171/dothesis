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
import logging

from langchain_core.tools import tool

from agent.sampling import target_sample_n

logger = logging.getLogger(__name__)

# Coordinating conjunctions (EN + VI) that usually mean an item bundles two
# ideas into one question ("fast AND reliable") — a double-barreled item the
# respondent can't answer cleanly. VI included because the default market is
# Vietnamese (project_sibling_products memory).
_CONJ = (" and ", " or ", " và ", " hoặc ")


_ATTENTION_TEMPLATES = {
    "en": ["For quality control, please select '{high}' for this item.",
           "Please answer '{low}' to show you are reading carefully.",
           "This is an attention check — select '{mid}'."],
    "vi": ["Để kiểm soát chất lượng, vui lòng chọn '{high}' cho mục này.",
           "Vui lòng chọn '{low}' để cho thấy bạn đang đọc kỹ.",
           "Đây là câu kiểm tra chú ý — hãy chọn '{mid}'."],
}


def _anchor_labels(language: str, likert_max: int):
    vi = str(language).lower().startswith("vi")
    if vi:
        return ("Hoàn toàn đồng ý", "Hoàn toàn không đồng ý", "Trung lập")
    return ("Strongly agree", "Strongly disagree", "Neither agree nor disagree")


def generate_attention_check_items(language: str = "en", likert_max: int = 5, n: int = 1) -> list[dict]:
    """Concrete, ready-to-drop attention-check items (deterministic). The student
    was told 'add an attention check'; this hands them one, phrased in their
    language and keyed to their scale — no more blank instruction."""
    high, low, mid = _anchor_labels(language, likert_max)
    tpls = _ATTENTION_TEMPLATES["vi" if str(language).lower().startswith("vi") else "en"]
    out = []
    for i in range(max(1, n)):
        t = tpls[i % len(tpls)]
        out.append({"id": f"AC{i + 1}", "construct": "_attention", "attention_check": True,
                    "expected_answer": {"high": high, "low": low, "mid": mid}[["high", "low", "mid"][i % 3]],
                    "text": t.format(high=high, low=low, mid=mid)})
    return out


def _keywords_i(text) -> set:
    import re as _re  # noqa: PLC0415
    stop = {"the", "and", "for", "of", "to", "a", "an", "in", "on", "scale", "construct"}
    return {w for w in _re.findall(r"[a-zà-ỹ]{4,}", str(text or "").lower()) if w not in stop}


def _suggest_source(construct: str, sources: list) -> str:
    """Best token-overlap match of a construct to an M2 source → 'Author (Year)'."""
    best, best_score = None, 0
    ckw = _keywords_i(construct)
    for s in (sources or []):
        if not isinstance(s, dict):
            continue
        score = len(ckw & _keywords_i(s.get("title")))
        if score > best_score:
            best, best_score = s, score
    if not best:
        return ""
    a = best.get("authors") or best.get("author")
    author = (a[0] if isinstance(a, list) and a else a) or "Author"
    author = str(author).split(",")[0].split()[-1] if author else "Author"
    return f"{author} ({best.get('year') or 'n.d.'})"


def audit_instrument_findings(instrument: dict, hypotheses: list[str], constructs: list[str],
                              sources: list | None = None, language: str = "en") -> dict:
    """Pure lint core. Returns {"findings", "scale_provenance", "suggested_attention_checks"}.

    Findings are all "soft" — advisory. Shared by the @tool below and the
    rubric's instrument_quality dimension. When `sources` (the M2 literature pool)
    is supplied, the scale-provenance rows are PRE-FILLED with the best-matching
    adapted-from citation instead of a blank skeleton (§3.4 generative depth).
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

    # 3) At least one attention check across the whole instrument — and hand the
    #    student a ready-made one instead of just saying "add one".
    suggested_ac: list = []
    if items and not any(it.get("attention_check") for it in items):
        suggested_ac = generate_attention_check_items(language, n=1)
        findings.append({
            "issue": "No attention-check item.",
            "fix": "Add at least one attention check — a ready-made item is provided in "
                   "`suggested_attention_checks`; drop it into the questionnaire.", "severity": "soft"})

    # Scale-provenance — one row per construct, PRE-FILLED with the best-matching
    # M2 source when a literature pool is supplied (§3.4), so "adapted_from" starts
    # from a real citation candidate the student confirms, not a blank the student
    # must research from scratch. An empty adapted_from is still the reminder.
    provenance = []
    for c in (constructs or []):
        suggested = _suggest_source(c, sources) if sources else ""
        provenance.append({"construct": c, "source": suggested, "adapted_from": suggested,
                           "back_translated": False,
                           "adapted_from_confirmed": False})
    return {"findings": findings, "scale_provenance": provenance,
            "suggested_attention_checks": suggested_ac}


@tool
def audit_instrument(instrument: dict, hypotheses: list[str], constructs: list[str],
                     sources: list | None = None, language: str = "en") -> str:
    """Lint AND scaffold a questionnaire before fielding.

    Checks for double-barreled/leading items, reverse-coded coverage per
    construct, and attention checks. GENERATES: `suggested_attention_checks`
    (ready-to-drop items keyed to the scale, in the survey language) and a
    scale-provenance table pre-filled with the best-matching adapted-from
    citation when `sources` (the M2 literature pool) is passed. Advisory —
    surface the findings + suggestions; never refuse to field.

    Args:
        instrument: {"items": [{"id", "text", "construct", "reverse_coded",
                     "attention_check"}, ...]}.
        hypotheses: the study's hypotheses (reserved for future cross-checks).
        constructs: construct names to check reverse-coded coverage for.
        sources: the M2 literature_sources pool, to pre-fill scale provenance.
        language: survey language ("en"/"vi") for generated attention checks.
    """
    return json.dumps(audit_instrument_findings(instrument, hypotheses, constructs,
                                                sources=sources, language=language),
                      ensure_ascii=False)


def build_consent_notice(language: str = "en", institution: str = "", purpose: str = "") -> str:
    """Deterministic informed-consent / data-privacy preamble for a survey.

    Folded in from the old "F14 ethics" line (F0 correction #5): every fielded
    instrument should open with a consent block — voluntary participation,
    anonymity, data use, withdrawal, and a contact. Bilingual because the default
    market is Vietnamese (project_sibling_products) with an English fallback for
    the intl (survify) audience. Advisory content the student adapts to their
    IRB/faculty rules; NOT legal advice.
    """
    vi = str(language).lower().startswith("vi")
    who = institution or ("nhóm nghiên cứu" if vi else "the research team")
    why = purpose or ("phục vụ mục đích học thuật" if vi else "academic research purposes")
    if vi:
        return (
            "THÔNG BÁO ĐỒNG THUẬN THAM GIA\n"
            f"Khảo sát này do {who} thực hiện, {why}.\n"
            "• Tham gia hoàn toàn tự nguyện; bạn có thể dừng bất cứ lúc nào.\n"
            "• Câu trả lời được ẩn danh và chỉ dùng cho mục đích nghiên cứu tổng hợp.\n"
            "• Dữ liệu được lưu trữ bảo mật và không chia sẻ thông tin định danh.\n"
            "• Bằng việc tiếp tục, bạn xác nhận đã đủ 18 tuổi và đồng ý tham gia."
        )
    return (
        "INFORMED CONSENT NOTICE\n"
        f"This survey is conducted by {who} for {why}.\n"
        "- Participation is entirely voluntary; you may stop at any time.\n"
        "- Your responses are anonymous and used only for aggregate research.\n"
        "- Data is stored securely and no identifying information is shared.\n"
        "- By continuing, you confirm you are 18+ and consent to participate."
    )


@tool
def consent_notice(language: str = "en", institution: str = "", purpose: str = "") -> str:
    """Generate an informed-consent / data-privacy preamble to place at the START
    of a survey before fielding.

    Covers voluntary participation, anonymity, data use, withdrawal, and consent.
    Bilingual (Vietnamese when language starts with 'vi', else English). Advisory
    ethics aid — adapt it to your institution's IRB/faculty requirements.
    """
    return build_consent_notice(language, institution, purpose)


def _max_in_degree(cm: dict) -> int:
    """Largest number of arrows pointing at any single construct — the widest
    regression in the model, i.e. the k that drives power (not total edges)."""
    edges = cm.get("edges") or cm.get("paths") or []
    indeg: dict = {}
    for e in edges:
        if isinstance(e, dict):
            tgt = e.get("target") or e.get("to")
            if tgt:
                indeg[tgt] = indeg.get(tgt, 0) + 1
    if indeg:
        return max(indeg.values())
    if cm.get("dependent_variable"):
        return len([v for v in (cm.get("independent_variables") or []) if v]) + (1 if cm.get("moderator") else 0)
    return 0


def make_sampling_plan_tool(store):
    """Wrap the sampling-plan computation as a LangChain tool bound to a store.

    Factory (closes over `store`) — mirrors make_preflight_tool. Two F0
    corrections drive this shape:
      1. The tool READS the project's live flat contextStore from the store; it
         does NOT take a model-supplied `context_store` argument (models can't be
         trusted to pass real state).
      2. The computed plan is PERSISTED to the owned M3 `sample_plan` key via
         commit_slice — the one write path — so it survives the turn and the
         preflight / field-it surfaces can read a real planned target_n. Writing
         it as an M3 design decision (not ephemeral coaching) is correct: a
         sample plan IS a design choice, and committing it flags M4 for review.
    """
    @tool
    def sampling_plan() -> str:
        """Compute a defensible target sample size + collection timeline from the
        study's method and model size, and record it in the design.

        Reads the project's chosen methodology, conceptual model, and instrument;
        applies the 10x / cases-per-predictor rules; and saves the plan so the
        methods pre-flight and Field-It handoff can use it. Returns the plan JSON.
        """
        cs = (store.load() or {}).get("contextStore") or {}
        method = cs.get("methodology") or "regression"
        cm = cs.get("conceptual_model") or {}
        inst = cs.get("instrument") or {}

        # Count structural paths across every M3 shape: edges/paths, or — for the
        # variable-decomposition shape — one path per independent variable (+1 for
        # a moderator). The old code read only `.paths`, so every nodes/edges or
        # decomposition model computed n_paths=0 → a wrong (too-small) sample.
        n_paths = len(cm.get("edges") or cm.get("paths") or [])
        if not n_paths and cm.get("dependent_variable"):
            ivs = [v for v in (cm.get("independent_variables") or []) if v]
            n_paths = len(ivs) + (1 if cm.get("moderator") else 0)

        # Count measured items across shapes: a flat instrument.items, else a
        # spec (constructs × items_per_construct), else per-node questions.
        n_ind = len(inst.get("items") or [])
        if not n_ind:
            try:
                per = int(inst.get("items_per_construct") or 0)
            except (TypeError, ValueError):
                per = 0
            n_constructs = len(inst.get("constructs") or cm.get("nodes") or [])
            if n_constructs and per:
                n_ind = n_constructs * per
            else:
                n_ind = sum(len((n or {}).get("questions") or [])
                            for n in (cm.get("nodes") or []) if isinstance(n, dict))
        n, rule = target_sample_n(method, n_paths, n_ind)

        # Power-primary sample size: a-priori power analysis is the committee-
        # facing justification; the heuristic becomes a floor. predictors =
        # MAX arrows into any one construct (the largest single regression),
        # not total edges. CB-SEM/AMOS defer power (fit-index based) → heuristic
        # only. Fail-open: any error keeps the heuristic-only plan.
        ml = method.lower()
        analysis = ("pls_sem" if "pls" in ml
                    else "regression" if ("regress" in ml or "spss" in ml) else None)
        if any(t in ml for t in ("cb-sem", "cbsem", "amos", "lavaan", "covariance")):
            analysis = None
        k = _max_in_degree(cm) or n_paths or 1
        power_analysis = None
        if analysis:
            try:
                import thesis_stats as ts  # noqa: PLC0415
                power_analysis = ts.run_power(analysis, "apriori", effect_size="medium",
                                              predictors=k)
                power_n = power_analysis.get("recommended_n") or power_analysis.get("required_n")
                if isinstance(power_n, int):
                    n = max(n, power_n)
            except Exception:
                logger.exception("sampling_plan: power analysis failed (fail-open)")
                power_analysis = None

        rationale = f"{rule} With {n_paths} structural paths and {n_ind} items."
        if power_analysis:
            rationale = (power_analysis["justification"] + " " + rationale +
                         " Recruit ~10–15% above target to absorb invalid/careless responses.")
        # Reconcile with the M1 early estimate (vision §3.1) so the two never look
        # contradictory — this computed plan supersedes it. Fail-open on any
        # malformed feasibility state.
        try:
            _feas = (cs.get("feasibility") or {}).get("sample_size") or {}
            _early = _feas.get("headline_n")
            if isinstance(_early, int):
                _k = (_feas.get("assumed") or {}).get("predictors")
                rationale += (f" Early M1 estimate was n ≈ {_early}"
                              + (f" (assumed {_k} predictors)" if _k else "")
                              + "; this plan supersedes it.")
        except Exception:
            logger.debug("sampling_plan: M1 reconciliation skipped", exc_info=True)
        plan = {
            "target_n": n,
            "method_rule": rule,
            "screening": "Add a screening question to exclude ineligible respondents.",
            # A bigger target needs a longer field window; keep it coarse.
            "timeline_weeks": 3 if n <= 250 else 4,
            "rationale": rationale,
        }
        if power_analysis:
            plan["power_analysis"] = power_analysis
        # Persist as an M3 design decision (F0 correction). Best-effort: a store
        # write failure must not lose the model the computed plan, so we still
        # return it — the persistence is advisory plumbing, not the deliverable.
        try:
            store.commit_slice("M3", {"sample_plan": plan},
                               reason="sampling_plan: computed target sample size")
        except Exception:
            logger.exception("sampling_plan: failed to persist sample_plan to store")
        return json.dumps(plan, ensure_ascii=False)

    return sampling_plan
