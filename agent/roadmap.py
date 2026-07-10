"""Derived coaching roadmap: a fixed display spine + position computed from
persisted artifacts (Approach A — state is truth, never narrated). Pure module:
no I/O, no LLM, so it's deterministic and trivially testable, and safe to import
from both the runtime (per-turn [NEXT] injection) and the API (roadmap endpoint).

The display spine is finer than the set of persisted checkpoints (some wizard
phases leave no artifact), so derivation SNAPS to the nearest persisted milestone
— it returns the first spine step whose backing artifact is absent. Steps before
it render as done, that step as current, later steps as upcoming.
"""
from __future__ import annotations

ROADMAP: dict[str, list[str]] = {
    "M1": ["frame_topic", "propose_titles", "confirm_title", "derive_questions"],
    "M2": ["familiarize", "map_research_state", "find_gaps", "confirm_refs", "generate_output"],
    "M3": ["define_constructs", "build_model", "state_hypotheses", "choose_method", "design_instrument"],
    "M4": ["detect_data", "outline_analysis", "confirm_plan", "run_per_step", "interpret"],
    # "review" (F3): a committee-readiness grade before export. Advisory, so
    # derive_substep never SNAPS to it (no backing artifact) — it's a display
    # spine step the review_thesis tool renders; export stays the terminal step.
    "M5": ["synthesize_sections", "assemble", "review", "export"],
}

SUBSTEP_LABELS: dict[str, str] = {
    "frame_topic": "Frame the topic", "propose_titles": "Propose titles",
    "confirm_title": "Confirm the title", "derive_questions": "Derive research questions",
    "familiarize": "Familiarize with the field", "map_research_state": "Map the research state",
    "find_gaps": "Find research gaps", "confirm_refs": "Confirm references",
    "generate_output": "Write the literature review",
    "define_constructs": "Define constructs", "build_model": "Build the conceptual model",
    "state_hypotheses": "State hypotheses", "choose_method": "Choose the method",
    "design_instrument": "Design the instrument",
    "detect_data": "Detect the dataset", "outline_analysis": "Outline the analysis",
    "confirm_plan": "Confirm the analysis plan", "run_per_step": "Run each analysis step",
    "interpret": "Interpret the results",
    "synthesize_sections": "Synthesize the chapters", "assemble": "Assemble the thesis",
    "review": "Committee-readiness review",
    "export": "Export the document",
}


def derive_substep(module: str, state: dict) -> str | None:
    """First spine sub-step whose persisted artifact is missing; None when the
    module's tracked artifacts are all present (ready to confirm done / done)."""
    cs = state.get("contextStore") or {}
    if module == "M1":
        if not cs.get("research_title"):
            return "frame_topic"
        if not cs.get("research_questions"):
            return "derive_questions"
        return None
    if module == "M2":
        if not cs.get("literature_sources"):
            return "familiarize"
        if not cs.get("research_gaps"):
            return "find_gaps"
        return None
    if module == "M3":
        if not cs.get("conceptual_model"):
            return "build_model"
        if not cs.get("hypotheses"):
            return "state_hypotheses"
        if not cs.get("methodology"):
            return "choose_method"
        return None
    if module == "M4":
        if not cs.get("analysis_outline"):
            return "outline_analysis"
        if not cs.get("analysis_results"):
            return "run_per_step"
        return None
    if module == "M5":
        if not cs.get("final_sections"):
            return "synthesize_sections"
        return None
    return None


from agent.state import MODULES  # ["M1".."M5"]  (import here: derive_substep above is dep-free)


def _title_for(module: str, substep: str | None) -> str:
    if substep is None:
        return f"Confirm {module} is done"
    return SUBSTEP_LABELS.get(substep, substep)


def next_action(state: dict) -> dict | None:
    """The single next thing the student should do. Deterministic precedence:
    open blocker > needs_review > advance focus > next module > done.

    Null-safe on headless-produced state (no roadmap_tasks, minimal status) so it
    never crashes an auto-mode / partner turn — the chat coaching layer must not
    couple into the headless surfaces.
    """
    cs = state.get("contextStore") or {}
    status = state.get("status") or {}
    focus = state.get("focus") or "M1"

    # 1) An open agent-inserted blocker jumps the queue.
    for t in cs.get("roadmap_tasks") or []:
        if t.get("status") == "open":
            return {"module": t.get("module", focus), "substep": t.get("substep", ""),
                    "title": t.get("title", "Resolve blocker"),
                    "why": t.get("why", "This is blocking progress."),
                    "cta_options": ["How do I fix this?", "Skip for now"]}

    # 2) A started module flagged for review beats marching forward.
    for m in MODULES:
        if status.get(m) == "needs_review":
            return {"module": m, "substep": derive_substep(m, state) or "",
                    "title": f"Re-check {m}",
                    "why": "An upstream change flagged it for review — resolve it before moving on.",
                    "cta_options": [f"Review {m}", "Why does this need review?"]}

    # 3) Advance the focus module.
    if status.get(focus) not in ("done", None) or derive_substep(focus, state) is not None:
        sub = derive_substep(focus, state)
        if sub is not None:
            return {"module": focus, "substep": sub, "title": _title_for(focus, sub),
                    "why": "This is the next step in your current module.",
                    "cta_options": [_title_for(focus, sub), "Skip to next module"]}
        if status.get(focus) != "done":
            return {"module": focus, "substep": "", "title": f"Confirm {focus} is done",
                    "why": f"{focus} has all its content — confirm it so we move on.",
                    "cta_options": [f"Mark {focus} done", "Not yet"]}

    # 4) Move to the first not-done module in order.
    for m in MODULES:
        if status.get(m) != "done":
            sub = derive_substep(m, state)
            return {"module": m, "substep": sub or "", "title": _title_for(m, sub),
                    "why": f"{focus} is done — {m} is next.",
                    "cta_options": [f"Start {m}", f"What does {m} involve?"]}

    # 5) Everything done.
    return {"module": "M5", "substep": "export", "title": "Export your thesis",
            "why": "Every module is done — generate the final document.",
            "cta_options": ["Export my thesis", "Review it first"]}
