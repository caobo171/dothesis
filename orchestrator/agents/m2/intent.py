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
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
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

    prompt = (
        f"You are classifying a user's reply during M2 Literature Review, "
        f"phase '{current_phase}'.\n"
        f"User reply: {text}\n\n"
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
        llm = _intent_llm().with_structured_output(PhaseIntent)
        intent = llm.invoke(prompt)
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
