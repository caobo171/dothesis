"""Phase 2 — Research_State."""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.tools.m2_literature import scout_citations

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "2_research_state.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "research_state"


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.5,
    )


def _scout(topic: str, min_n: int = 20) -> list[dict]:
    # Indirection allows monkeypatching in tests without touching the tool itself
    return scout_citations.invoke({"topic": topic, "min_n": min_n})


def _synthesize(state: M2SubGraphState, refinements: list[str]) -> str:
    # Uses the module-level _get_llm() so tests can monkeypatch it
    citations = state.get("research_state_citations", [])
    citations_block = "\n".join(
        f"- {c.get('authors', '?')} ({c.get('year', '?')}). {c.get('title', '?')}."
        for c in citations[:30]
    )
    refinement_block = ""
    if refinements:
        refinement_block = "User refinements:\n" + "\n".join(f"- {r}" for r in refinements)
    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Topic: {state.get('research_title')}\n"
        f"Research type: {state.get('research_type')}\n"
        f"Language: {state.get('language')}\n\n"
        f"Citations available:\n{citations_block}\n\n"
        f"{refinement_block}"
    )
    return _get_llm().invoke(user_prompt).content


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # Auto mode: scout → synthesize → advance in one shot
    if mode == "auto":
        citations = state.get("research_state_citations") or _scout(state.get("research_title", ""))
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=[])
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )

    # First call: no draft yet — scout citations and synthesize
    if not state.get("research_state_draft"):
        citations = _scout(state.get("research_title", ""))
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=state.get("research_state_refinements", []))
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "research_state_confirmed": False,
            "messages": [AIMessage(content=draft)],
        }

    # Draft exists: classify what the user wants to do with it
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    if intent.action == "navigate":
        # Navigate back to a prior phase
        return {"current_phase": intent.target_phase or "familiarize"}

    if intent.action == "confirm":
        return {
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    if intent.action == "refine":
        counts = dict(state.get("regeneration_count") or {})
        current_count = counts.get(_PHASE_KEY, 0)
        if current_count >= _regen_cap():
            # Hit the cap — block further regen and prompt the user
            return {
                "messages": [AIMessage(content=(
                    f"We've regenerated {_regen_cap()} times — let's lock this in "
                    "or move on. Reply 'confirm' to advance, or 'force-continue' "
                    "to bypass the cap once."
                ))],
            }
        counts[_PHASE_KEY] = current_count + 1
        refinements = list(state.get("research_state_refinements") or []) + [
            intent.refinement_text or last_user
        ]
        new_state = dict(state)
        new_state["research_state_refinements"] = refinements
        # Reuse cached citations — no re-scout on refine
        draft = _synthesize(new_state, refinements=refinements)
        return {
            "research_state_refinements": refinements,
            "regeneration_count": counts,
            "research_state_draft": draft,
            "messages": [AIMessage(content=draft)],
        }

    # Ambiguous input — ask for clarification
    return {
        "messages": [AIMessage(content=(
            "I'm not sure what you'd like. Reply 'confirm' to advance, "
            "or describe how you'd like the synthesis changed."
        ))],
    }
