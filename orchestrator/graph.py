"""LangGraph topology — supervisor in the middle, 5 module agents on the spokes.

Architecture: START → supervisor → (M1|M2|M3|M4|M5|END)
              each module node → supervisor (loop until DONE)

The supervisor uses rule-based routing (next_unconfirmed_module) and, in
interactive mode, also fires an LLM intent classifier when the user's message
contains navigation keywords (e.g. "go back", "skip").
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m1_topic import M1Agent
from orchestrator.agents.m2_literature import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.agents.supervisor import route_from_supervisor, supervisor_node
from orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module agent singletons — one instance per process is enough because
# ModuleAgent.step() is stateless (all mutable data lives in OrchestratorState).
# ---------------------------------------------------------------------------
_AGENT_BY_KEY = {
    "M1": M1Agent(),
    "M2": M2Agent(),
    "M3": M3Agent(),
    "M4": M4Agent(),
    "M5": M5Agent(),
}

# Maps the graph's node key (M1..M5) to the ContextStore field it owns.
_MODULE_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


def _agent_node_factory(module_key: str):
    """Wrap a ModuleAgent.step() into a LangGraph node function.

    Decision: the factory closes over module_key so we get five distinct node
    functions from one template — avoids duplicating the state-patch logic five
    times.  The returned patch writes only the two keys we know changed
    (messages + context_store), leaving every other state field untouched.
    """
    def _node(state: OrchestratorState) -> dict:
        from langchain_core.messages import AIMessage

        agent = _AGENT_BY_KEY[module_key]
        result = agent.step(state)

        # Deep-copy the ContextStore and stamp the module's confirmed output so
        # future supervisor invocations see the confirmed_at timestamp and skip
        # this module.
        cs = state["context_store"].model_copy(deep=True)
        setattr(cs, _MODULE_FIELD[module_key], result.context_patch)

        return {
            "messages": [AIMessage(content=result.assistant_message)],
            "context_store": cs,
        }

    # Assign a meaningful __name__ for LangGraph's graph visualisation / logging.
    _node.__name__ = f"agent_{module_key.lower()}_node"
    return _node


def build_graph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    """Compile the orchestrator graph.

    Args:
        interactive: When True the graph halts *before* each supervisor visit
            so the HTTP layer can stream the previous module's reply and collect
            the next user message.  When False (auto-mode) the graph runs to END
            without any interrupts.
        checkpointer: LangGraph checkpoint backend.  Tests pass MemorySaver;
            production passes a PostgresSaver backed by a psycopg_pool.

    Returns:
        A compiled CompiledStateGraph ready for .invoke() / .stream().
    """
    builder = StateGraph(OrchestratorState)

    # Supervisor is the central hub — every spoke flows back through it.
    builder.add_node("supervisor", supervisor_node)

    # Register one spoke node per module using the factory above.
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_node(key, _agent_node_factory(key))

    # Execution always begins at the supervisor so it can route even on the
    # very first invocation (e.g. when current_module is pre-seeded to "M1").
    builder.add_edge(START, "supervisor")

    # The supervisor's route_from_supervisor() reads state["current_module"]
    # and returns the node name to go to next (or "DONE" which maps to END).
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"M1": "M1", "M2": "M2", "M3": "M3",
         "M4": "M4", "M5": "M5", "DONE": END},
    )

    # Each module node loops back to the supervisor after completing its step.
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_edge(key, "supervisor")

    # In interactive mode we interrupt *before* the supervisor so the HTTP
    # layer can inject the next user message between turns.  In auto-mode the
    # list is empty and the graph runs end-to-end.
    interrupt_before = ["supervisor"] if interactive else []

    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


# ---------------------------------------------------------------------------
# Singleton accessors — the FastAPI app and the subprocess each get one cached
# instance backed by the real Postgres checkpointer.
# ---------------------------------------------------------------------------

_pool = None


def _get_pool():
    """Lazy psycopg connection pool used by PostgresSaver.

    Decision: We pool here so multiple concurrent agent invocations reuse
    connections rather than opening a new socket per request.  LangGraph 1.x's
    PostgresSaver expects a pool (not a raw connection) for thread safety.
    """
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            # autocommit=True is required by LangGraph's PostgresSaver which
            # manages its own transaction boundaries.
            kwargs={"autocommit": True},
        )
    return _pool


@lru_cache(maxsize=1)
def get_interactive_graph():
    """Returns the cached in-process graph used by the chat router.

    saver.setup() is idempotent — it creates LangGraph's internal checkpoint
    tables on first run and is a no-op on subsequent calls.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_graph(interactive=True, checkpointer=saver)


@lru_cache(maxsize=1)
def get_auto_graph():
    """Returns the cached auto-mode graph used by the subprocess entrypoint (__main__.py)."""
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_graph(interactive=False, checkpointer=saver)
