"""M2 per-phase intent classifier — LLM-first, no keyword catches.

Auto mode short-circuits to confirm. Interactive mode always asks gemini-2.5-flash
to pick the action; regex still extracts structured data (gap IDs, page numbers)
because those are bounded patterns, not natural-language phrasing.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


PhaseKey = Literal[
    "familiarize", "research_state", "gap_analysis",
    "reference_confirm", "output_gen",
]


class PhaseIntent(BaseModel):
    action: Literal[
        "confirm", "refine", "navigate", "select", "skip", "skip_all",
        "correct_page", "add_custom_gap",
    ] = "confirm"
    refinement_text: str = ""
    target_phase: PhaseKey | None = None
    selected_ids: list[str] = Field(default_factory=list)
    corrected_page: int | None = None
    custom_gap_text: str = ""


def _intent_llm():
    # timeout matches base.py:_get_llm; without it, a stalled Gemini call here
    # could block every M2 interactive turn. See the L1/L2 fixes for the
    # supervisor + base.py hot-path equivalents.
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def classify_phase_intent(
    *,
    last_user_message: str,
    current_phase: PhaseKey,
    mode: Literal["interactive", "auto"],
) -> PhaseIntent:
    # Auto mode always advances — no user confirmation needed.
    if mode == "auto":
        return PhaseIntent(action="confirm")

    text = (last_user_message or "").strip()
    if not text:
        return PhaseIntent(action="confirm")

    # Regex extracts structured data (bounded patterns, not language matching).
    # These overlay on top of the LLM-classified action below.
    selected_ids = re.findall(r"\bgap\s*(\d+)\b", text.lower())
    page_match = re.search(r"page\s+(\d+)", text.lower())

    # Phase-specific decision context. The generic action list below describes
    # actions by their reference_confirm/gap_analysis meaning, which leaves the
    # familiarize phase (a simple "use my papers vs. let you search" fork) with
    # no clean mapping — e.g. "no papers, just use AI search" got classified as
    # refine/navigate and the phase re-asked forever. Spelling out the fork lets
    # the model map both branches onto confirm/skip, which phase 1 advances on.
    phase_context = {
        "familiarize": (
            "In THIS phase the user decides whether to use their uploaded papers "
            "or let you search for sources. Map their reply:\n"
            "- confirm: use the uploaded papers (yes / use them / go ahead).\n"
            "- skip: they have no papers or want you to search instead "
            "(no papers / just use AI search / I don't have any / proceed / "
            "search for me).\n"
            "Either branch ADVANCES — only avoid confirm/skip if the user is "
            "asking a question or wants to do something else entirely.\n\n"
        ),
    }.get(current_phase, "")

    prompt = (
        f"You are classifying a user's reply during M2 Literature Review, "
        f"phase '{current_phase}'.\n"
        f"User reply: {text}\n\n"
        f"{phase_context}"
        f"Pick the SINGLE best action:\n"
        f"- confirm: agrees with current output / wants to advance (yes / sure / "
        f"looks good / move on / đồng ý / etc.)\n"
        f"- refine: wants the agent to redo or rework with different guidance "
        f"(e.g. 'focus on X instead', 'redo this', 'change Y')\n"
        f"- navigate: wants to jump back to an earlier phase (e.g. 'go back to "
        f"the gap step', 'redo the research state'). Set target_phase to one "
        f"of: familiarize / research_state / gap_analysis / reference_confirm / "
        f"output_gen.\n"
        f"- select: picking specific gap IDs (gap_analysis phase only)\n"
        f"- skip: skip the current reference (reference_confirm phase only)\n"
        f"- skip_all: skip ALL remaining references\n"
        f"- correct_page: providing a correct page number\n"
        f"- add_custom_gap: adding a user-defined gap (gap_analysis phase only). "
        f"Set custom_gap_text to the user's message.\n\n"
        f"For 'refine', set refinement_text to the user's message."
    )
    try:
        from orchestrator.agents.base import bounded_invoke
        llm = _intent_llm().with_structured_output(PhaseIntent)
        # Wall-clock-bounded: a stalled Gemini call here would block every M2
        # interactive turn. The existing except-block degrades to refine on
        # any failure including BoundedInvokeTimeout, so M2 never hangs.
        intent = bounded_invoke(
            llm, prompt,
            max_seconds=int(os.getenv("ORCHESTRATOR_LLM_MAX_SECONDS", "25")),
            retries=0,
        )
        # Backfill structured data from regex when the LLM didn't extract it.
        if intent.action == "select" and not intent.selected_ids and selected_ids:
            intent.selected_ids = selected_ids
        if intent.action == "correct_page" and intent.corrected_page is None and page_match:
            intent.corrected_page = int(page_match.group(1))
        if intent.action == "add_custom_gap" and not intent.custom_gap_text:
            intent.custom_gap_text = last_user_message
        if intent.action == "refine" and not intent.refinement_text:
            intent.refinement_text = last_user_message
        return intent
    except Exception:  # noqa: BLE001 - LLM failure falls back to refine
        logger.exception("M2 phase-intent classification failed; defaulting to refine")
        return PhaseIntent(action="refine", refinement_text=last_user_message)
