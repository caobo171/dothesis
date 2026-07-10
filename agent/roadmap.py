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
    "M5": ["synthesize_sections", "assemble", "export"],
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
