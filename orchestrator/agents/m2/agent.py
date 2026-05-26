"""M2Agent — outer-graph wrapper that delegates to the M2 sub-graph.

Decision: M2 uses a dedicated 5-phase sub-graph rather than the generic
ModuleAgent clarification loop.  This wrapper seeds the sub-graph from outer
state, invokes it, and flattens the result back into a ModuleStepResult so the
outer graph sees a uniform interface.
"""
from __future__ import annotations

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.agents.m2.graph import get_m2_graph
from orchestrator.agents.m2.translation import _flatten_to_m2_output, _seed_from_outer
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


class M2Agent(ModuleAgent):
    schema = M2Output
    module_key = "M2"
    system_prompt = _PROMPT
    tools = [scout_citations, summarize_paper, find_research_gaps,
             compile_citations, verify_page_numbers]

    def step(self, state) -> ModuleStepResult:
        with _open_db_session() as db:
            sub_state = _seed_from_outer(state, db)

        is_interactive = state.get("mode", "interactive") == "interactive"
        sub_graph = get_m2_graph(interactive=is_interactive)
        # Use thread_id::m2 so the sub-graph checkpoint is scoped under the outer thread.
        # Fall back to "unknown" if caller did not set thread_id (e.g. unit tests).
        outer_thread = state.get("thread_id") or "unknown"
        config = {"configurable": {"thread_id": f"{outer_thread}::m2"}}
        final = sub_graph.invoke(sub_state, config=config)

        if final.get("current_phase") == "DONE":
            return ModuleStepResult(
                assistant_message=(
                    f"M2 complete — {len(final.get('citation_list', []))} citations, "
                    f"draft of Chapter 2 ready."
                ),
                context_patch=_flatten_to_m2_output(final),
                transition=True,
            )

        msgs = final.get("messages") or []
        latest = msgs[-1].content if msgs else ""
        return ModuleStepResult(
            assistant_message=latest,
            context_patch=_flatten_to_m2_output(final),
            transition=False,
            needs_user_reply=True,
        )
