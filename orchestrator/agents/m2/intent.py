"""M2 per-phase intent classifier.

Hybrid rules-first / LLM-fallback. In auto mode, always returns confirm.
"""
from __future__ import annotations

import os
import re
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field


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


_CONFIRM_WORDS = {
    "yes", "y", "ok", "okay", "looks good", "confirm", "go", "continue",
    "đồng ý", "ok rồi", "tiếp tục", "tốt rồi",
}
_REFINE_KEYWORDS = ("redo", "regenerate", "change", "focus on", "instead",
                    "làm lại", "đổi", "tập trung vào")
_NAV_KEYWORDS_TO_PHASE: dict[str, PhaseKey] = {
    "back to research state": "research_state",
    "back to research": "research_state",
    "back to gap": "gap_analysis",
    "back to references": "reference_confirm",
    "redo familiarize": "familiarize",
    "go to research state": "research_state",
    "go to gap": "gap_analysis",
    "quay lại nghiên cứu": "research_state",
    "quay lại gap": "gap_analysis",
}
_SKIP_ALL_WORDS = {"skip all", "skip the rest", "bỏ qua tất cả"}
_SKIP_WORDS = {"skip", "next", "bỏ qua"}


def _intent_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.0,
    )


def classify_phase_intent(
    *,
    last_user_message: str,
    current_phase: PhaseKey,
    mode: Literal["interactive", "auto"],
) -> PhaseIntent:
    # Auto mode always advances — no user confirmation needed
    if mode == "auto":
        return PhaseIntent(action="confirm")

    text = (last_user_message or "").strip().lower()

    # Navigation back to a prior phase takes highest priority
    for kw, target in _NAV_KEYWORDS_TO_PHASE.items():
        if kw in text:
            return PhaseIntent(action="navigate", target_phase=target)

    # Phase 3: gap selection or custom gap insertion
    if current_phase == "gap_analysis":
        ids = re.findall(r"\bgap\s*(\d+)\b", text)
        if ids:
            return PhaseIntent(action="select", selected_ids=ids)
        if "custom gap" in text or "add gap" in text:
            return PhaseIntent(action="add_custom_gap",
                                custom_gap_text=last_user_message)

    # Phase 4: skip/skip-all/page-correction rules
    if current_phase == "reference_confirm":
        if any(kw in text for kw in _SKIP_ALL_WORDS):
            return PhaseIntent(action="skip_all")
        page_match = re.search(r"page\s+(\d+)", text)
        if page_match and ("correct" in text or "actually" in text):
            return PhaseIntent(action="correct_page",
                                corrected_page=int(page_match.group(1)))
        if any(kw in text for kw in _SKIP_WORDS):
            return PhaseIntent(action="skip")

    # Generic refine keywords
    if any(kw in text for kw in _REFINE_KEYWORDS):
        return PhaseIntent(action="refine", refinement_text=last_user_message)

    # Confirm words: exact match, prefix, or as a whole word within the text
    # e.g. "looks good, continue" should match "continue" even mid-sentence
    if any(
        text == w or text.startswith(w + " ") or
        re.search(r"\b" + re.escape(w) + r"\b", text)
        for w in _CONFIRM_WORDS
    ):
        return PhaseIntent(action="confirm")

    # Ambiguous — fall back to LLM structured-output classification
    try:
        llm = _intent_llm().with_structured_output(PhaseIntent)
        prompt = (
            f"Classify the user's intent in M2 Literature Review phase '{current_phase}'.\n"
            f"User message: {last_user_message}\n"
            "If unclear, default to 'refine' with the message as refinement_text."
        )
        return llm.invoke(prompt)
    except Exception:
        return PhaseIntent(action="refine", refinement_text=last_user_message)
