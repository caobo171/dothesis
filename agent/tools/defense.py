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


def committee_questions(context_store: dict, rubric_result: dict | None = None) -> list[dict]:
    """Back-compat pure API: the ranked viva question list for THIS thesis.

    Delegates to agent.viva.generate_viva (roadmap #10): every material rubric
    finding + three state-direct signals (power shortfall, not-supported
    hypotheses, data-quality flags) + the four staples, ranked must_fix →
    disclosable → standard. Returns just the `questions` list; the store-bound
    tool returns the full envelope (with readiness)."""
    from agent.viva import generate_viva  # noqa: PLC0415
    return generate_viva(context_store or {}, rubric_result)["questions"]


def make_defense_tools(store) -> list:
    """Build the defense tool(s) bound to one project's state store.

    Factory closes over `store` (F0 correction) so the tool reads the project's
    real state instead of a model-supplied argument. Registered in
    agent/runtime.py's tool list."""

    @tool
    def generate_committee_questions() -> str:
        """Generate a defense-readiness viva targeted at THIS thesis's weak points.

        Returns a JSON envelope: `questions` (each with category, difficulty,
        `defensibility` = must_fix|disclosable|standard, a grounded
        `model_answer_hint`, and `answer_criteria` to grade answers against),
        plus `readiness` (verdict not_ready|ready_with_disclosures|ready, must_fix
        / disclosable counts, per-dimension tally). must_fix items (number
        mismatches, unverifiable citations, provably-wrong stats) must be FIXED
        before the defense, not talked past. Read-only over thesis state."""
        from agent.viva import generate_viva  # noqa: PLC0415
        cs = store.load_full_context_store()
        # Best-effort rubric so the viva targets the examiner's likely attack
        # points. Any failure (missing key, judge LLM down) → state-only viva.
        rubric = None
        try:
            from quality.rubric import score_thesis  # noqa: PLC0415
            rubric = score_thesis(
                cs, institution_profile=store.get_institution_profile() or None,
                advisor_feedback=store.get_advisor_feedback() or [])
        except Exception:
            logger.exception("generate_committee_questions: rubric pass failed; state-only")
            rubric = None
        return json.dumps(generate_viva(cs, rubric), ensure_ascii=False)

    return [generate_committee_questions]
