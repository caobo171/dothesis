"""M2Agent — outer-graph wrapper that delegates to the M2 sub-graph.

Decision: M2 uses a dedicated 5-phase sub-graph rather than the generic
ModuleAgent clarification loop.  This wrapper seeds the sub-graph from outer
state, invokes it, and flattens the result back into a ModuleStepResult so the
outer graph sees a uniform interface.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.agents.m2.graph import get_m2_graph
# PR #5: M2 declared as the PhaseChat shape per brief §3. ModuleAgent
# stays in the MRO so the legacy step() helpers (clarification dispatch,
# widget render hints) keep working — PhaseChatAgent.step is abstract but
# is provided by ModuleAgent further down the MRO. The shape declaration
# documents the contract without disturbing behavior.
from orchestrator.agents.shapes import PhaseChatAgent
from orchestrator.agents.m2.translation import _flatten_to_m2_output, _seed_from_outer
from orchestrator.message_utils import text_of
from orchestrator.schemas.m2 import M2Output
from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)

_PROMPT = (
    "M2 Literature Review wrapper. Routes the user through a 5-phase "
    "chat-first conversation (familiarize → research state → gap analysis "
    "→ reference confirm → output generation)."
)


def _open_db_session():
    """Return a DB session context manager.

    Kept as a plain function (not @contextmanager) so tests can monkeypatch it
    with `lambda: FakeDbSession()` without needing to mimic a generator.
    """
    from app.db import get_session_factory
    sf = get_session_factory()
    return sf()


class M2Agent(PhaseChatAgent, ModuleAgent):
    # PhaseChatAgent FIRST in the MRO so isinstance(M2Agent(), PhaseChatAgent)
    # is True (shapes assertion) but ModuleAgent.step() resolves first when
    # walked for the actual implementation — Python ABC accepts this because
    # PhaseChatAgent.step is abstract and ModuleAgent.step is concrete.
    schema = M2Output
    module_key = "M2"
    slice_field = "m2_literature"  # brief §6 — ModuleHandler contract
    system_prompt = _PROMPT
    tools = [scout_citations, summarize_paper, find_research_gaps,
             compile_citations, verify_page_numbers]

    def step(self, state) -> ModuleStepResult:
        with _open_db_session() as db:
            sub_state = _seed_from_outer(state, db)

        # Look up the chat router's progress emitter from the engine.utils.
        # progress registry keyed by thread_id. CRITICAL: the emitter must NOT
        # go in graph state — LangGraph's postgres checkpointer msgpack-
        # serializes state and crashes on functions ('Type is not msgpack
        # serializable: function'). Registry is per-process, set + cleared by
        # the chat router around astream; absent in tests / sim / auto CLI.
        try:
            from engine.utils import progress as _progress
            emitter = _progress.lookup(state.get("thread_id"))
        except Exception:  # noqa: BLE001 — engine progress is best-effort
            emitter = None
        if emitter is not None:
            sub_state["_progress_emitter"] = emitter
            # Always-fires entry beat. Without this, M2 turns that don't
            # run scout (gap_analysis / reference_confirm / output_gen
            # phases — any "do it" after the first research_state confirm)
            # leave the UI on a typing dot for the whole LLM call: those
            # phases have no per-step heartbeats of their own. This single
            # emit is the smallest change that guarantees ProgressBubble
            # gets one event per M2 turn so the user sees we're working.
            current_phase = (
                (state.get("context_store").m2_literature or {}).get("_phase_state", {}).get("current_phase")
                or "familiarize"
            ) if state.get("context_store") else "familiarize"
            try:
                emitter({
                    "stage": "m2.phase",
                    "message": f"📚 M2 — running {current_phase} phase…",
                    "phase": current_phase,
                })
            except Exception:  # noqa: BLE001 — emitter is best-effort
                pass

        if state.get("mode", "interactive") != "interactive":
            return self._auto_step(state, sub_state)
        return self._interactive_step(state, sub_state)

    def _auto_step(self, state, sub_state) -> ModuleStepResult:
        """Auto-mode: run the M2 sub-graph straight through to DONE.

        Auto-mode compiles the sub-graph with no interrupts, so a single invoke
        walks every phase to completion — this path works as-is and stays
        sub-graph-driven. (Interactive can't use it: interrupt_before pauses
        BEFORE a phase runs, so it never produces the phase's question.)
        """
        sub_graph = get_m2_graph(interactive=False)
        outer_thread = state.get("thread_id") or "unknown"
        config = {"configurable": {"thread_id": f"{outer_thread}::m2"}}
        final = sub_graph.invoke(sub_state, config=config)
        return ModuleStepResult(
            assistant_message=(
                f"M2 complete — {len(final.get('citation_list', []))} citations, "
                f"draft of Chapter 2 ready."
            ),
            context_patch=_flatten_to_m2_output(final),
            transition=final.get("current_phase") == "DONE",
        )

    def _interactive_step(self, state, sub_state) -> ModuleStepResult:
        """Interactive: dispatch the M2 phase functions directly, one chat turn
        at a time, with phase state persisted through the outer context store.

        Decision: the M2 sub-graph's interactive mode used interrupt_before on
        every phase node, which pauses BEFORE the node runs — so the wrapper's
        single invoke produced no question (empty reply), and re-seeding a fresh
        sub-state each turn reset current_phase to "familiarize" (phase amnesia).
        Together with the outer routing loop that was the "stuck after confirming
        M1" bug. The phase .run() functions are already standalone (the phase
        tests call them directly), so we drive them here without the checkpointed
        sub-graph: run phases until one PAUSES (leaves current_phase unchanged →
        it's waiting on the user) or we reach DONE. Each phase runs at most once
        per turn, so the user's reply is consumed only by the first (resuming)
        phase; any later phase reached this turn is a fresh first-call that emits
        its own opening question.
        """
        from orchestrator.agents.m2.phases import (
            phase1_familiarize, phase2_research_state, phase3_gap_analysis,
            phase4_reference_confirm, phase5_output_gen,
        )
        phase_modules = {
            "familiarize": phase1_familiarize,
            "research_state": phase2_research_state,
            "gap_analysis": phase3_gap_analysis,
            "reference_confirm": phase4_reference_confirm,
            "output_gen": phase5_output_gen,
        }

        # Seed the user's latest message ONLY when resuming M2 (a prior turn
        # already persisted _phase_state, i.e. M2 asked something and this reply
        # answers it). On the FIRST entry to M2 the triggering message was M1's
        # confirmation ("yes"), which the supervisor used to advance into M2 in
        # the SAME turn — feeding that "yes" to phase 1's intent classifier made
        # it skip the opening question and barrel into phase 2's citation scout.
        # On first entry we pass no message so phase 1 just asks its question.
        m2_slice = state["context_store"].m2_literature or {}
        is_resume = "_phase_state" in m2_slice
        last_user = next(
            (m for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            None,
        )
        sub_state["messages"] = (
            [HumanMessage(content=text_of(last_user))]
            if (is_resume and last_user) else []
        )

        emitted: list = []
        # Bounded by the number of phases (+1) — a phase that doesn't advance
        # breaks the loop, so at most one run per distinct phase. The cap is a
        # belt-and-braces guard against a phase that both advances AND loops.
        for _ in range(len(phase_modules) + 1):
            phase = sub_state.get("current_phase", "familiarize")
            if phase == "DONE":
                break
            patch = phase_modules[phase].run(sub_state)
            sub_state = {**sub_state, **patch}
            emitted.extend(patch.get("messages") or [])
            # The first phase has now consumed the user's reply — clear it so a
            # later phase reached this same turn treats itself as a first-call
            # rather than re-interpreting the stale reply as its own answer.
            sub_state["messages"] = []
            if sub_state.get("current_phase", phase) == phase:
                break  # phase stayed put → waiting on the user → pause the turn

        out = _flatten_to_m2_output(sub_state)
        if sub_state.get("current_phase") == "DONE":
            return ModuleStepResult(
                assistant_message=(
                    f"M2 complete — {len(sub_state.get('citation_list', []))} "
                    f"citations, draft of Chapter 2 ready."
                ),
                context_patch=out,
                transition=True,
            )

        latest = text_of(emitted[-1]) if emitted else ""
        # W1: surface any widget hint a phase attached (card_grid for phase 1
        # choices, gap cards for phase 3, …) so graph.py:77 can put it on the
        # outbound AIMessage and the frontend WidgetRenderer can draw it.
        # Source of truth: the most recently emitted AIMessage's
        # additional_kwargs.tool_calls_json — the phase puts it there too, so
        # this stays consistent even if a phase forgets to include it as a
        # separate patch key.
        hint = None
        if emitted:
            hint = (getattr(emitted[-1], "additional_kwargs", {}) or {}
                    ).get("tool_calls_json")
        if hint is None:
            hint = sub_state.get("tool_calls_json")
        return ModuleStepResult(
            assistant_message=latest,
            context_patch=out,
            transition=False,
            needs_user_reply=True,
            tool_calls_json=hint,
        )
