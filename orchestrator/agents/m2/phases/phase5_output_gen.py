"""Phase 5 — Output_Gen. Single-shot, no regen loop."""
from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage
from orchestrator.llm import get_orchestrator_llm

from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "5_output_gen.md").read_text(encoding="utf-8")
_STYLE = (_PROMPT_DIR / "_style.md").read_text(encoding="utf-8")


def _get_llm():
    # Delegates to the engine-wide factory (ORCHESTRATOR_LLM_ROUTE routes the
    # whole engine); temperature 0.4 is this phase's original per-site setting.
    return get_orchestrator_llm(temperature=0.4)


def _format_references(refs: list[dict]) -> str:
    """Format sources without inventing or demanding page anchors."""
    lines = []
    for r in refs:
        page = r.get("page")
        page_part = f", p. {page}" if r.get("verified") and page is not None else ""
        lines.append(f"- {r.get('author')} ({r.get('year')}){page_part}")
    return "\n".join(lines)


def _format_gaps(gaps: list[dict], selected: list[str]) -> str:
    selected_set = set(selected or [])
    return "\n".join(
        f"- {g.get('description', '?')}"
        for g in gaps if str(g.get("id")) in selected_set
    )


def run(state: M2SubGraphState) -> dict:
    synthesis = state.get("research_state_draft", "")
    selected_gaps = _format_gaps(
        state.get("candidate_gaps") or [],
        state.get("selected_gap_ids") or [],
    )
    refs = _format_references(state.get("verified_refs") or [])

    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Topic: {state.get('research_title')}\n"
        f"Research type: {state.get('research_type')}\n"
        f"Language: {state.get('language')}\n\n"
        f"Phase 2 synthesis:\n{synthesis}\n\n"
        f"Confirmed research gaps:\n{selected_gaps}\n\n"
        f"Grounded references:\n{refs}"
    )
    draft = _get_llm().invoke(user_prompt).content

    return {
        "ch2_draft": draft,
        "citation_list": state.get("research_state_citations") or [],
        "current_phase": "DONE",
        "messages": [AIMessage(content="Chapter 2 drafted.")],
    }
