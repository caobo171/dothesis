"""LangGraph topology v2 — single conversational router, modules as tools.

Architecture: START → _seed → router_agent_node → END

Replaces the v1 hub-and-spoke graph (supervisor → M1..M5 → supervisor →
END) with a single node whose body picks the right module per turn and
runs it. Modules themselves are unchanged in Stage 1 — see
orchestrator/agents/module_tools.py and orchestrator/agents/router_agent.py.

## Why a single node (and not a sub-graph)

The router itself can call AT MOST ONE module per turn (Stage 1
contract — see router_agent.py docstring). There's no second hop to
model, so we don't need conditional edges or a nested sub-graph. One
node keeps the SSE adapter trivial (the chat router gets exactly one
update event per user turn, just like it did with the v1 module nodes).

## Why a separate file (not a flag inside graph.py)

Easy to delete in Phase D once v2 has soaked. Easy to A/B in CI. And
the v1 graph.py is unchanged byte-for-byte except for the env-flag
branch in init_interactive_graph — so we can pull the rip-cord by
flipping ORCHESTRATOR_ROUTER back to v1 without diffing across files.
"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.router_agent import route_turn
from orchestrator.state import (
    OrchestratorState, compute_status_map, propagate_needs_review,
)

logger = logging.getLogger(__name__)

# Map module key → ContextStore field. Mirrors graph.py:_MODULE_FIELD —
# duplicated to keep this file independent of graph.py (Phase D collapses
# the two; until then no cross-import).
_MODULE_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


def _seed_state_node(state: OrchestratorState) -> dict:
    """Pre-router seeder — identical contract to graph.py:_seed_state_node.

    Duplicated rather than imported so graph_v2.py has no v1 dependencies
    and Phase D can remove graph.py without leaving dangling imports.
    """
    from orchestrator.state import ContextStore
    patch: dict = {}
    if "context_store" not in state:
        patch["context_store"] = ContextStore()
    if "mode" not in state:
        patch["mode"] = "interactive"
    return patch


def router_agent_node(state: OrchestratorState) -> dict:
    """The single node that owns every interactive turn in v2.

    Calls route_turn (which short-circuits or asks the LLM to pick a
    module), runs the picked module's step(), and produces a state
    patch in the SAME shape v1's _agent_node_factory emits. That shape
    parity is what lets the SSE adapter stay (mostly) unchanged.
    """
    # PR #2b — route_turn now also returns the intent (continue/read/mutate).
    # Older callers got (picked, result); handle both shapes so a stubbed
    # route_turn in tests doesn't have to know about the third element.
    routed = route_turn(state)
    if len(routed) == 3:
        picked, result, intent = routed
    else:
        picked, result = routed                                # type: ignore[misc]
        intent = "continue"

    # Snapshot the PRE-mutate context store for propagation decisions.
    # propagate_needs_review walks status BEFORE this turn's writes — we want
    # to flag downstream modules that WERE done, not modules that this very
    # turn just touched.
    pre_cs = state["context_store"]

    cs = pre_cs.model_copy(deep=True)
    setattr(cs, _MODULE_FIELD[picked], result.context_patch)

    # Brief §1.5 — intent classification + propagation.
    #
    # We classify per-turn from (focus, picked, slice_changed) rather than
    # asking the LLM for an explicit intent label. Rationale:
    #   - The LLM already picked `target` (via route_turn). Adding a second
    #     classification call would double the routing latency for no gain.
    #   - The picked vs focus comparison is deterministic and matches the
    #     brief's "mutate to a non-focus module" definition exactly.
    #   - Read intent (no write, no focus shift) is NOT handled in this PR —
    #     today's route_turn always invokes the module step. A follow-up
    #     adds the read handler + a third intent.
    #
    # The "did the slice actually change?" guard prevents propagation on
    # turns where the module step paused for user input without writing
    # (e.g. clarification questions) — those aren't mutates per §1.5.
    focus = state.get("focus")
    slice_changed = result.context_patch != (getattr(pre_cs, _MODULE_FIELD[picked]) or {})
    # Defense in depth: intent=='read' MUST never propagate, even if a
    # future read_handler accidentally returns a modified slice. Belt-and-
    # braces — the no-write guard alone would catch it, but explicit
    # intent gating means a code review can spot a regression without
    # tracing through the slice-comparison logic.
    is_cross_module_mutate = (
        intent == "mutate"
        and slice_changed
        and focus is not None
        and picked != focus
    )

    if is_cross_module_mutate:
        # Propagate against the PRE-mutate store — that's where the "was it
        # done before this edit?" check lives. The resulting downstream
        # markers then merge into the post-mutate slice via model_copy.
        propagated = propagate_needs_review(pre_cs, mutated=picked)
        # Bring the downstream slice markers across — re-apply our own
        # context_patch on top so the picked module's writes win.
        for m_field in (
            "m1_topic", "m2_literature", "m3_design",
            "m4_analysis", "m5_writing",
        ):
            if m_field == _MODULE_FIELD[picked]:
                continue
            setattr(cs, m_field, getattr(propagated, m_field))

    ai = AIMessage(content=result.assistant_message)
    if result.tool_calls_json:
        ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

    messages = [ai]
    if result.extra_messages:
        messages.extend(result.extra_messages)

    # Focus follows the brief §1.5 rule:
    #   - cold-start (focus=None) → seed from picked (first turn's module is
    #     the initial focus, by definition).
    #   - mutate (cross-module write) → shift focus to target.
    #   - read → leave focus alone (brief §1.5: "focus stays put").
    #   - continue (same-module work) → leave focus alone.
    # Read explicitly skipped from the focus shift even when target != focus;
    # that's the whole point of read vs mutate.
    if focus is None:
        new_focus = picked
    elif is_cross_module_mutate:
        new_focus = picked
    else:
        new_focus = focus

    # Recompute the status map AFTER the mutate + propagation. Persisted on
    # state so callers (the chat router, the UI sidebar) see the post-turn
    # truth without re-deriving it from context_store themselves.
    new_status = compute_status_map(cs)

    return {
        "messages": messages,
        "context_store": cs,
        # Stamp current_module + last_tool_called so the SSE adapter and
        # downstream callers can see which module owned this turn — the
        # v1 graph encoded this in the LangGraph node_name, but v2 has
        # only one node so the identity has to ride on state.
        "current_module": picked,
        "last_tool_called": picked,
        # Brief §1.4 — focus + status carried on state. PR #2 starts writing
        # them; downstream PRs (web UI, persistence) start reading.
        "focus": new_focus,
        "status": new_status,
        # _module_paused kept for API parity: True when the module is
        # waiting on the user. In v1 this drove the conditional edge
        # back to supervisor vs END; in v2 we always END after the
        # router node (one tool per turn), so the flag is informational
        # for tests / introspection only.
        "_module_paused": not result.transition,
    }


def build_graph_v2(*, checkpointer: BaseCheckpointSaver):
    """Compile the v2 (router-agent) graph.

    Note `interactive` parameter is NOT exposed — auto-mode stays on v1
    in Stage 1 (see plan: Phase C). graph.py's build_graph keeps owning
    that surface.
    """
    builder = StateGraph(OrchestratorState)
    builder.add_node("_seed", _seed_state_node)
    builder.add_node("router_agent_node", router_agent_node)
    builder.add_edge(START, "_seed")
    builder.add_edge("_seed", "router_agent_node")
    builder.add_edge("router_agent_node", END)
    return builder.compile(checkpointer=checkpointer)
