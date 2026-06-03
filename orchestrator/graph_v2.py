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
from orchestrator.state import OrchestratorState

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
    picked, result = route_turn(state)

    cs = state["context_store"].model_copy(deep=True)
    setattr(cs, _MODULE_FIELD[picked], result.context_patch)

    ai = AIMessage(content=result.assistant_message)
    if result.tool_calls_json:
        ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

    messages = [ai]
    if result.extra_messages:
        messages.extend(result.extra_messages)

    return {
        "messages": messages,
        "context_store": cs,
        # Stamp current_module + last_tool_called so the SSE adapter and
        # downstream callers can see which module owned this turn — the
        # v1 graph encoded this in the LangGraph node_name, but v2 has
        # only one node so the identity has to ride on state.
        "current_module": picked,
        "last_tool_called": picked,
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
