"""Phase 1 — Familiarize."""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "1_familiarize.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.4,
    )


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")
    paper_uris = state.get("paper_uris", [])

    # Auto mode: skip conversational loop — set fact and advance
    if mode == "auto":
        return {
            "has_uploaded_papers": bool(paper_uris),
            "current_phase": "research_state",
        }

    if state.get("has_uploaded_papers") is None:
        last_user = next(
            (m.content for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        # If there is user input, check whether it's a confirm/skip intent
        if last_user.strip():
            intent = classify_phase_intent(
                last_user_message=last_user,
                current_phase="familiarize",
                mode="interactive",
            )
            if intent.action in {"confirm", "skip"}:
                # "confirm" means they agree to use uploaded papers (if any),
                # "skip" means they want to skip upload and use AI search
                return {
                    "has_uploaded_papers": (intent.action == "confirm") or bool(paper_uris),
                    "current_phase": "research_state",
                }

        # First turn (or non-actionable input): ask the opening question
        if paper_uris:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has {len(paper_uris)} uploaded paper(s). "
                f"Ask whether to use them as primary citation sources, or fall back to AI search."
            )
        else:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has no uploaded papers. "
                f"Ask whether the user wants to upload some, or proceed with AI search."
            )
        msg = _get_llm().invoke(user_prompt).content
        return {
            "messages": [AIMessage(content=msg)],
            "has_uploaded_papers": None,
        }

    # has_uploaded_papers already resolved — advance to next phase
    return {"current_phase": "research_state"}
