"""Phase 3 — Gap_Analysis."""
from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.message_utils import text_of


def _build_gap_hint(gaps: list[dict]) -> dict:
    """Build a multi-select card_grid where each gap is one card. Users
    typically pick multiple gaps together (the synthesis chapter often weaves
    2-3 gaps into one argument), so single-select would force a serial click
    loop. multi_select=True lets the widget queue selections client-side and
    only fire once on Submit."""
    options = [
        CardOption(
            value=str(g.get("id", i + 1)),
            label=str(g.get("description", "?"))[:120],
            description=f"Relevance: {g.get('relevance', 'Medium')}",
        )
        for i, g in enumerate(gaps)
    ]
    # W5: escape hatch — opens text input where the user describes a gap not
    # in the LLM's list. Routed by the synthesizer into add_custom_gap intent.
    options.append(CardOption(
        value="Other",
        label="Add a different gap",
        description=("Opens a text box; describe the gap you want addressed "
                     "and I'll fold it into the list."),
    ))
    return CardGridHint(
        widget_type="card_grid",
        field_name="selected_gap_ids",
        title="Which research gaps should this thesis address?",
        options=options,
        columns=2,
        multi_select=True,
    ).model_dump()

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "3_gap_analysis.md").read_text(encoding="utf-8")
_STYLE = (_PROMPT_DIR / "_style.md").read_text(encoding="utf-8")

_PHASE_KEY = "gap_analysis"


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
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


# Author/year values the LLM produces when it has no real citations.
# Includes the placeholder strings we saw in the wild ('Author', 'Year', 'page?')
# and the generic schema-example values from the prompt ('X', 'Y', '...').
_PLACEHOLDER_AUTHOR_TOKENS = {
    "author", "x", "y", "z", "...", "…", "n/a", "na",
    "name", "first", "last", "lastname", "firstname",
}
_PLACEHOLDER_YEAR_TOKENS = {"year", "...", "…", "n/a", "na", ""}


def _is_real_paper(paper: dict) -> bool:
    """Heuristic guard against the literal-placeholder strings the LLM emits
    when it has no real citations to use. Drops papers with author values like
    'Author', 'X' or year values like 'Year' / 'page?' / non-int strings.

    Conservative: only drops obvious placeholders; real edge cases (e.g.
    one-word author 'Smith') survive.
    """
    if not isinstance(paper, dict):
        return False
    author = str(paper.get("author", "")).strip().lower()
    if not author or author in _PLACEHOLDER_AUTHOR_TOKENS:
        return False
    year = paper.get("year")
    if isinstance(year, str):
        if year.strip().lower() in _PLACEHOLDER_YEAR_TOKENS:
            return False
        try:
            year = int(year)
        except ValueError:
            return False
    if isinstance(year, int):
        if year < 1800 or year > 2100:
            return False
    elif year is not None:
        return False
    return True


def _generate_gaps(state: M2SubGraphState, refinements: list[str]) -> list[dict]:
    # B2 HARD GUARD: never call the LLM if there are no real citations. Without
    # sources the LLM fabricates placeholder strings ({"author":"Author"}) which
    # then make their way through phase4 verification as "Citation: Author
    # (Year) page page?". Refuse instead.
    if not state.get("research_state_citations"):
        return []

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
        if not isinstance(gaps, list):
            return []
    except (json.JSONDecodeError, TypeError):
        return []

    # B2 defense-in-depth: filter placeholder supporting_papers even if the
    # LLM was given citations. Some models still slip placeholder JSON in.
    cleaned: list[dict] = []
    for g in gaps:
        gd = dict(g)
        papers = gd.get("supporting_papers", []) or []
        gd["supporting_papers"] = [p for p in papers if _is_real_paper(p)]
        cleaned.append(gd)
    return cleaned


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
        if not gaps:
            # B2 user-visible message: don't show "Here are the gaps:" with an
            # empty list. Either there were no citations (phase2 gate should
            # have caught this, but defense-in-depth) or the LLM returned
            # nothing usable. Either way, the user needs a clear explanation.
            text = (
                "I can't propose research gaps without real citations. "
                "Please go back to the literature step (say 'go back') and "
                "give me different search terms, or upload papers."
            )
            return {
                "candidate_gaps": [],
                "messages": [AIMessage(content=text)],
            }
        text = "Here are the gaps I found:\n" + "\n".join(
            f"  {g.get('id', i+1)}. {g.get('description', '?')} ({g.get('relevance', 'Medium')})"
            for i, g in enumerate(gaps)
        ) + "\n\nWhich would you like to use? Pick one or more from the cards below."
        # W2: surface the gap list as a multi-select card_grid. The text above
        # stays as the conversation log for accessibility and for clients that
        # haven't rendered widgets, but the cards are the primary UI.
        hint = _build_gap_hint(gaps)
        ai = AIMessage(content=text, additional_kwargs={"tool_calls_json": hint})
        return {
            "candidate_gaps": gaps,
            "messages": [ai],
            "tool_calls_json": hint,
        }

    last_user = next(
        (text_of(m) for m in reversed(state.get("messages") or [])
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
