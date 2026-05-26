"""Phase 3 — Gap_Analysis."""
from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "3_gap_analysis.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "gap_analysis"


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.3,
    )


def _strip_fence(s: str) -> str:
    """Strip markdown code fences if present."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _generate_gaps(state: M2SubGraphState, refinements: list[str]) -> list[dict]:
    refinement_block = ""
    if refinements:
        refinement_block = "\nUser constraints:\n" + "\n".join(f"- {r}" for r in refinements)
    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Synthesis from Phase 2:\n{state.get('research_state_draft', '')}\n"
        f"{refinement_block}"
    )
    resp = _get_llm().invoke(user_prompt).content
    try:
        gaps = json.loads(_strip_fence(resp))
        if isinstance(gaps, list):
            return [dict(g) for g in gaps]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # Auto mode: generate all gaps and select them all in one shot
    if mode == "auto":
        gaps = _generate_gaps(state, refinements=[])
        return {
            "candidate_gaps": gaps,
            "selected_gap_ids": [g.get("id", str(i)) for i, g in enumerate(gaps)],
            "current_phase": "reference_confirm",
        }

    # First call: no gaps proposed yet
    if not state.get("candidate_gaps"):
        gaps = _generate_gaps(state, refinements=state.get("gap_refinements", []))
        text = "Here are the gaps I found:\n" + "\n".join(
            f"  {g.get('id', i+1)}. {g.get('description', '?')} ({g.get('relevance', 'Medium')})"
            for i, g in enumerate(gaps)
        ) + "\n\nWhich would you like to use? (e.g. 'use gap 1 and gap 3')"
        return {
            "candidate_gaps": gaps,
            "messages": [AIMessage(content=text)],
        }

    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    if intent.action == "navigate":
        return {"current_phase": intent.target_phase or "research_state"}

    if intent.action == "select":
        return {
            "selected_gap_ids": intent.selected_ids,
            "current_phase": "reference_confirm",
        }

    if intent.action == "add_custom_gap":
        existing = list(state.get("candidate_gaps") or [])
        new_id = str(len(existing) + 1)
        existing.append({
            "id": new_id,
            "description": intent.custom_gap_text or last_user,
            "relevance": "Medium",
            "supporting_papers": [],
            "confirmed": True,
        })
        return {
            "candidate_gaps": existing,
            "messages": [AIMessage(content=f"Added gap {new_id}. Want me to re-list?")],
        }

    if intent.action == "refine":
        counts = dict(state.get("regeneration_count") or {})
        current_count = counts.get(_PHASE_KEY, 0)
        if current_count >= _regen_cap():
            # Cap hit — don't call LLM, prompt user to select from existing list
            return {
                "messages": [AIMessage(content=(
                    f"We've regenerated {_regen_cap()} times. "
                    "Pick from the current list or 'force-continue' to bypass."
                ))],
            }
        counts[_PHASE_KEY] = current_count + 1
        refinements = list(state.get("gap_refinements") or []) + [intent.refinement_text or last_user]
        gaps = _generate_gaps(state, refinements=refinements)
        text = "Here's a revised list:\n" + "\n".join(
            f"  {g.get('id', i+1)}. {g.get('description', '?')}"
            for i, g in enumerate(gaps)
        )
        return {
            "candidate_gaps": gaps,
            "gap_refinements": refinements,
            "regeneration_count": counts,
            "messages": [AIMessage(content=text)],
        }

    return {
        "messages": [AIMessage(content=(
            "I'm not sure — say 'use gap N' to pick, or describe how to refine the list."
        ))],
    }
