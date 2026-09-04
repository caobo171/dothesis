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
    "M2": ["familiarize", "map_research_state", "find_gaps", "generate_output"],
    "M3": ["define_constructs", "build_model", "state_hypotheses", "choose_method", "design_instrument"],
    "M4": ["detect_data", "outline_analysis", "confirm_plan", "run_per_step", "interpret"],
    # M5 owns the closing pair — Discussion + Conclusion — not the whole
    # document. Every module composes its own chapter as it completes
    # (orchestrator.tools.m5_writing.MODULE_CHAPTERS), so by the time a student
    # reaches M5 chapters 1-4 already exist; "synthesize the chapters" and
    # "assemble the thesis" described the pre-continuous-writing job.
    #
    # The "review" step (a committee-readiness grade sitting between assembly
    # and export) is gone. It put a review in front of the student's output,
    # which is backwards — they get the document, then fine-tune it. The
    # review_thesis tool still exists and still grades on demand; it just isn't
    # a step anyone has to walk through first. Export is terminal.
    "M5": ["write_discussion", "write_conclusion", "export"],
}

SUBSTEP_LABELS: dict[str, str] = {
    "frame_topic": "Frame the topic", "propose_titles": "Propose titles",
    "confirm_title": "Confirm the title", "derive_questions": "Derive research questions",
    "familiarize": "Familiarize with the field", "map_research_state": "Map the research state",
    "find_gaps": "Find research gaps",
    "generate_output": "Write the literature review",
    "define_constructs": "Define constructs", "build_model": "Build the conceptual model",
    "state_hypotheses": "State hypotheses", "choose_method": "Choose the method",
    "design_instrument": "Design the instrument",
    "detect_data": "Detect the dataset", "outline_analysis": "Outline the analysis",
    "confirm_plan": "Confirm the analysis plan", "run_per_step": "Run each analysis step",
    "interpret": "Interpret the results",
    "write_discussion": "Write the discussion", "write_conclusion": "Write the conclusion",
    "export": "Export the document",
}


# Which spine sub-steps have a PERSISTED artifact backing them, and which
# contextStore key proves it. Listed in spine order per module.
#
# The rest of the spine (propose_titles, confirm_title, map_research_state,
# define_constructs, detect_data, …) is unbacked: real work with
# nothing durable to check, so its completion can only ever be inferred from
# position. Keeping the split explicit here is the point — it used to be
# implicit in derive_substep's if-chain, which meant nothing else could ask
# "is this step actually evidenced?" without restating the mapping.
SUBSTEP_ARTIFACT: dict[str, dict[str, str]] = {
    "M1": {"frame_topic": "research_title", "derive_questions": "research_questions"},
    "M2": {"familiarize": "literature_sources", "find_gaps": "research_gaps"},
    "M3": {"build_model": "conceptual_model", "state_hypotheses": "hypotheses",
           "choose_method": "methodology"},
    "M4": {"outline_analysis": "analysis_outline", "run_per_step": "analysis_results"},
    # `final_sections` is where M5's composed prose lands (both the discussion
    # and the conclusion live in it), so it backs the first of the pair. Once it
    # exists, derivation moves past write_discussion; write_conclusion is
    # unbacked, the same way most spine steps are.
    "M5": {"write_discussion": "final_sections"},
}


def satisfied_substeps(module: str, state: dict) -> set[str]:
    """Backed sub-steps whose artifact is actually present.

    Separate from derive_substep because "where are you working" and "what have
    you finished" stopped being the same question once mid-journey import
    landed: reconstruct_upstream can infer a LATER artifact without an earlier
    one (research_gaps with no literature_sources — it can name the gaps a
    finished thesis addresses, but it must never invent the source list). A
    strictly linear spine can't express that, so completion is read from the
    artifacts rather than from how far along the current step is.
    """
    cs = state.get("contextStore") or {}
    return {sid for sid, key in SUBSTEP_ARTIFACT.get(module, {}).items() if cs.get(key)}


def derive_substep(module: str, state: dict) -> str | None:
    """First spine sub-step whose persisted artifact is missing; None when the
    module's tracked artifacts are all present (ready to confirm done / done).

    Order comes from ROADMAP, so this and SUBSTEP_ARTIFACT cannot drift out of
    step the way two hand-maintained if-chains would.
    """
    backed = SUBSTEP_ARTIFACT.get(module, {})
    if not backed:
        return None
    have = satisfied_substeps(module, state)
    for sid in ROADMAP[module]:
        if sid in backed and sid not in have:
            return sid
    return None


from agent.state import MODULES  # ["M1".."M5"]  (import here: derive_substep above is dep-free)


def _title_for(module: str, substep: str | None) -> str:
    if substep is None:
        return f"Confirm {module} is done"
    return SUBSTEP_LABELS.get(substep, substep)


def next_action(state: dict, required: frozenset[str] | None = None) -> dict | None:
    """The single next thing the student should do. Deterministic precedence:
    open blocker > advance focus > next module > done.

    Null-safe on headless-produced state (no roadmap_tasks, minimal status) so it
    never crashes an auto-mode / partner turn — the chat coaching layer must not
    couple into the headless surfaces.

    `required` (partner reports) narrows module advancement to the modules the
    ordered chapters actually need: without it a 3-chapter order still marched the
    agent through a full M4 analysis it never asked for (~10 min of run_stats
    churn that blew the wall-clock). None → all five modules (interactive default).
    """
    cs = state.get("contextStore") or {}
    status = state.get("status") or {}
    focus = state.get("focus") or "M1"
    # Modules this run is allowed to steer toward. A non-required module is
    # treated as out-of-scope for focus-advance and next-module, so the roadmap
    # routes M3 → M5 directly when M4 isn't ordered.
    eligible = required or frozenset(MODULES)

    # 1) An open agent-inserted blocker jumps the queue.
    for t in cs.get("roadmap_tasks") or []:
        if t.get("status") == "open":
            return {"module": t.get("module", focus), "substep": t.get("substep", ""),
                    "title": t.get("title", "Resolve blocker"),
                    "why": t.get("why", "This is blocking progress."),
                    "cta_options": ["How do I fix this?", "Skip for now"]}

    # A `needs_review` branch used to sit here, ahead of everything below: any
    # module invalidated by an upstream edit hijacked "what's next" into
    # "Re-check M2 — resolve it before moving on". Removed deliberately. Stale
    # modules are still tracked (state["stale"]) and still shown, but the
    # student is never sent backwards to clear a flag before they can keep
    # going — output first, fine-tuning after.

    # 2) Advance the focus module — only if it's a module this run needs. A
    #    focus parked on an out-of-scope module (e.g. M4 on a no-Results order)
    #    falls through to step 4, which routes to the next REQUIRED module.
    if focus in eligible and (
            status.get(focus) not in ("done", None) or derive_substep(focus, state) is not None):
        sub = derive_substep(focus, state)
        if sub is not None:
            return {"module": focus, "substep": sub, "title": _title_for(focus, sub),
                    "why": "This is the next step in your current module.",
                    "cta_options": [_title_for(focus, sub), "Skip to next module"]}
        if status.get(focus) != "done":
            return {"module": focus, "substep": "", "title": f"Confirm {focus} is done",
                    "why": f"{focus} has all its content — confirm it so we move on.",
                    "cta_options": [f"Mark {focus} done", "Not yet"]}

    # 3) Move to the first not-done REQUIRED module in order.
    for m in MODULES:
        if m in eligible and status.get(m) != "done":
            sub = derive_substep(m, state)
            return {"module": m, "substep": sub or "", "title": _title_for(m, sub),
                    "why": f"{focus} is done — {m} is next.",
                    "cta_options": [f"Start {m}", f"What does {m} involve?"]}

    # 4) Everything done. Lead into the mock committee (F6) alongside export —
    #    the emotional peak of the journey, not just a file drop. substep stays
    #    "export" (the terminal spine step); defense prep is an optional
    #    rehearsal offered via the CTA, not a tracked module.
    return {"module": "M5", "substep": "export",
            "title": "Export your thesis & prep your defense",
            "why": "Every module is done — generate the final document and rehearse your defense.",
            "cta_options": ["Export my thesis", "Prep for my defense", "Review it first"]}
