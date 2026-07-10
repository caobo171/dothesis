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
        n_paths = len((cs.get("conceptual_model") or {}).get("paths") or [])
        n_ind = len((cs.get("instrument") or {}).get("items") or [])
        n, rule = target_sample_n(method, n_paths, n_ind)
        plan = {
            "target_n": n,
            "method_rule": rule,
            "screening": "Add a screening question to exclude ineligible respondents.",
            # A bigger target needs a longer field window; keep it coarse.
            "timeline_weeks": 3 if n <= 250 else 4,
            "rationale": f"{rule} With {n_paths} structural paths and {n_ind} items.",
        }
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
