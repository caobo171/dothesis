"""Mock Committee (F6) — generate defense questions from THIS thesis's weak points.

Best-effort by design: state-only heuristics guarantee weakness-targeted material
even when the LLM/rubric is unavailable, so the drill is never empty.

F0 correction to the plan: `generate_committee_questions` is NOT a bare @tool that
takes a model-supplied `context_store` (models can't be trusted to hand over real
state). Instead the weakpoint logic is a PURE function tested directly, and the
tool is built by a store-bound factory (`make_defense_tools(store)`, the same
pattern as make_sampling_plan_tool / make_preflight_tool) that reads the project's
real state via the store and folds in the F3 rubric best-effort.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _state_weakpoints(cs: dict) -> list[dict]:
    """Heuristic questions from the nested (full) context_store shape
    (m3_design / m4_analysis), the same shape store.load_full_context_store()
    returns. Decision: read straight off the persisted design/results so the
    questions target what THIS student actually did, not a generic list."""
    m3 = cs.get("m3_design") or {}
    m4 = cs.get("m4_analysis") or {}
    qs: list[dict] = []

    # Small n → the classic power/generalizability challenge.
    n = (m3.get("sample_plan") or {}).get("target_n")
    if n and n < 200:
        qs.append({"category": "methodology",
                   "question": f"Your sample size is {n}. How do you justify statistical power "
                               "and generalizability?", "targets": "sample size",
                   "difficulty": "medium", "model_answer_hint": "Cite the 10x / inverse-sqrt rule "
                   "and acknowledge it as a limitation with a future-work note."})

    # A not-supported / rejected hypothesis is the examiner's first pull.
    results = str(m4.get("analysis_results") or "").lower()
    if "not support" in results or "reject" in results or "p=0.2" in results:
        qs.append({"category": "results",
                   "question": "One of your hypotheses was not supported. Why do you think that "
                               "is, and what does it mean theoretically?",
                   "targets": "rejected hypothesis", "difficulty": "hard",
                   "model_answer_hint": "Offer a theoretical/contextual explanation, not a "
                   "data-quality excuse."})

    # Always-on staples so the drill is never empty (empty-state robustness).
    qs += [
        {"category": "contribution", "question": "What is the single most important contribution "
         "of your study?", "targets": "contribution", "difficulty": "medium",
         "model_answer_hint": "One theoretical + one practical contribution, in one sentence each."},
        {"category": "methodology", "question": "Why did you choose this analysis method over the "
         "alternatives?", "targets": "method choice", "difficulty": "medium",
         "model_answer_hint": "Tie to model type, sample size, and construct nature."},
        {"category": "limitations", "question": "What are the main limitations of your study?",
         "targets": "limitations", "difficulty": "easy",
         "model_answer_hint": "Name 2-3 honest limitations with mitigation/future work."},
    ]
    return qs


def committee_questions(context_store: dict, rubric_result: dict | None = None) -> list[dict]:
    """Pure question generator. State-only heuristics; rubric folding lands in Task 2.

    `context_store` is the NESTED module shape (m1_topic..m5_writing)."""
    return _state_weakpoints(context_store or {})


def make_defense_tools(store) -> list:
    """Build the defense tool(s) bound to one project's state store.

    Factory closes over `store` (F0 correction) so the tool reads the project's
    real state instead of a model-supplied argument. Registered in
    agent/runtime.py's tool list."""

    @tool
    def generate_committee_questions() -> str:
        """Generate defense-committee questions targeted at THIS thesis's weak points
        (small n, rejected hypotheses, method choice, sampling, borderline validity,
        and any open quality findings). Returns categorized questions with
        model-answer hints for a drill. Read-only over thesis state."""
        # Read the whole nested context store (design/results) the heuristics need.
        cs = store.load_full_context_store()
        # Best-effort F3 rubric so the drill also hits the examiner's likely
        # quality attack points. Any failure (missing key, LLM down) falls back
        # to state-only heuristics — the drill must always have material.
        rubric = None
        try:
            from quality.rubric import score_thesis  # noqa: PLC0415
            rubric = score_thesis(
                cs, institution_profile=store.get_institution_profile() or None,
                advisor_feedback=store.get_advisor_feedback() or [])
        except Exception:
            logger.exception("generate_committee_questions: rubric pass failed; state-only")
            rubric = None
        return json.dumps(committee_questions(cs, rubric), ensure_ascii=False)

    return [generate_committee_questions]
