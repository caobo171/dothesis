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
from orchestrator.agents.m2 import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.agents.supervisor import route_from_supervisor, supervisor_node
from orchestrator.state import ContextStore, OrchestratorState

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

        # Attach tool_calls_json to additional_kwargs only when present so
        # empty-dict pollution is avoided for the common case where no widget
        # hint is emitted.  The chat router (Task 6) reads this key to decide
        # whether to stream a UI widget alongside the text reply.
        ai = AIMessage(content=result.assistant_message)
        if result.tool_calls_json:
            ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

        # SP5: forward extra_messages (M4's per-step execution emissions).
        # The chat router's SSE loop already handles N messages per LangGraph
        # update — see api/app/routers/chat.py gen().
        messages = [ai]
        if result.extra_messages:
            messages.extend(result.extra_messages)

        return {
            "messages": messages,
            "context_store": cs,
            # Universal pause signal for the conditional edge below. transition
            # True → module advanced (go to supervisor); False → module is
            # waiting on the user (end the turn). See OrchestratorState.
            "_module_paused": not result.transition,
        }

    # Assign a meaningful __name__ for LangGraph's graph visualisation / logging.
    _node.__name__ = f"agent_{module_key.lower()}_node"
    return _node


def _make_route_after_module(module_key: str):
    """Closure: routing decision for the conditional edge from a module node.

    Decision: replaces the previous static `interrupt_after=[M1..M5]` on the
    compiled graph. interrupt_after fired unconditionally after every visit
    to a module, which meant when M1 transitioned to M2 the turn ended right
    after M1 emitted "Confirmed M1. Moving on." — the user had to send
    another message before M2's first question appeared. That broke the
    intuitive "confirm and immediately see the next step" UX.

    With the conditional edge:
      - If the module paused for user input (ModuleStepResult.transition is
        False → state["_module_paused"] is True) → route to END, ending the
        astream. Checkpoint preserves state for the next user message.
      - If the module just transitioned (transition True) → route back to
        supervisor, which then routes to the next module IN THE SAME ASTREAM
        CALL. M2 emits its first question, hits its own routing, and END fires.
        The user sees M1's confirmation + M2's first question in a single turn.

    Decision: key off the universal _module_paused flag (written by every module
    node from ModuleStepResult.transition) rather than sniffing per-module
    _awaiting_field / _awaiting_confirm markers out of the context slice. The
    old marker-sniffing only recognised the base ModuleAgent clarification loop
    (M1/M4/M5); M2 and M3 carry their own phase pointers and never set those
    markers, so the router mistook a paused M2 for a finished M2 and looped
    supervisor↔M2 until GraphRecursionError — which the chat router swallowed,
    leaving the user with no reply (the "stuck forever after confirming M1" bug).
    """
    # module_key is closed over for parity with the rest of the factory family
    # and to keep the per-edge function names distinct in graph visualisations.
    _ = module_key

    def _route(state: OrchestratorState) -> str:
        return "end" if state.get("_module_paused") else "supervisor"
    return _route


def _seed_state_node(state: OrchestratorState) -> dict:
    """Pre-supervisor seeder for missing required fields.

    Decision: callers like the FastAPI chat router seed `context_store` from
    Postgres before the first turn, but other front-doors (LangSmith Studio,
    direct LangGraph SDK calls, ad-hoc Python REPL exploration) typically only
    submit `{messages: [...]}` on the first turn — and the supervisor reads
    `state["context_store"]` unconditionally, so it would KeyError.
    Returning a partial patch here is safe: LangGraph merges by key, so when
    the chat router already populated the fields the patch stays empty and
    nothing is overwritten. When fields are missing we seed empty defaults so
    every direct LangGraph caller works without knowing about the contract.
    """
    patch: dict = {}
    if "context_store" not in state:
        patch["context_store"] = ContextStore()
    if "mode" not in state:
        # Default to interactive mode — auto-mode is reserved for the
        # subprocess entrypoint which seeds mode itself.
        patch["mode"] = "interactive"
    return patch


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

    # Seed node fills any missing required state fields before the supervisor
    # reads them. See _seed_state_node docstring for the contract rationale.
    builder.add_node("_seed", _seed_state_node)

    # Supervisor is the central hub — every spoke flows back through it.
    builder.add_node("supervisor", supervisor_node)

    # Register one spoke node per module using the factory above.
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_node(key, _agent_node_factory(key))

    # Execution flows START → _seed → supervisor so the supervisor can rely on
    # context_store + mode being populated even when the caller submits the
    # minimal `{messages: [...]}` state (Studio, raw SDK calls).
    builder.add_edge(START, "_seed")
    builder.add_edge("_seed", "supervisor")

    # The supervisor's route_from_supervisor() reads state["current_module"]
    # and returns the node name to go to next (or "DONE" which maps to END).
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"M1": "M1", "M2": "M2", "M3": "M3",
         "M4": "M4", "M5": "M5", "DONE": END},
    )

    # Each module routes either back to supervisor (continue same turn after
    # transition) or to END (pause for user reply). See _make_route_after_module
    # for the contract. Replaces the previous static interrupt_after which
    # always paused after M1, hiding M2's first question behind an extra turn.
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_conditional_edges(
            key,
            _make_route_after_module(key),
            {"supervisor": "supervisor", "end": END},
        )

    # `interactive` is preserved as a parameter for API stability — both modes
    # now use the same topology. Auto-mode never hits the END-routing branch
    # because _auto_fill transitions immediately, so supervisor just keeps
    # routing through the module chain until M5 confirms → supervisor →
    # DONE → END. No checkpointer interrupts needed in either mode.
    _ = interactive  # retained for compat; routing handles both modes

    return builder.compile(checkpointer=checkpointer)


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

        # SQLAlchemy uses URLs like `postgresql+psycopg://...` but psycopg's
        # native parser rejects the `+psycopg` driver suffix. Strip it so the
        # same DATABASE_URL works for both SQLAlchemy and psycopg_pool.
        url = os.environ["DATABASE_URL"]
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)

        _pool = ConnectionPool(
            url,
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            # autocommit=True is required by LangGraph's PostgresSaver which
            # manages its own transaction boundaries.
            kwargs={"autocommit": True},
            # Same reason the async pool below sets this, same database: DATABASE_URL
            # points at a REMOTE Postgres, an idle pooled connection over a WAN gets
            # reaped by NAT/firewall timeouts without either end noticing, and the pool
            # then hands out a corpse that dies mid-query with "server closed the
            # connection unexpectedly". check_connection turns that into a
            # discard-and-replace inside the pool. The async twin has had this since
            # it was written; the sync one it sits twenty lines above never did.
            check=ConnectionPool.check_connection,
        )
    return _pool


_async_pool = None
_interactive_graph = None


async def _get_async_pool():
    """Lazy AsyncConnectionPool used by AsyncPostgresSaver.

    Decision: the chat router calls graph.astream(), which dispatches to the
    checkpointer's aget_tuple — only AsyncPostgresSaver implements that.
    The sync PostgresSaver raises NotImplementedError on the async path.
    """
    global _async_pool
    if _async_pool is None:
        from psycopg_pool import AsyncConnectionPool

        url = os.environ["DATABASE_URL"]
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        _async_pool = AsyncConnectionPool(
            url,
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            kwargs={"autocommit": True},
            # Validate a connection before handing it out. DATABASE_URL points at
            # a REMOTE Postgres in dev, and an idle pooled connection over a WAN
            # gets reaped by NAT/firewall timeouts without either end noticing —
            # the pool then hands out a corpse and the caller dies mid-query with
            # "server closed the connection unexpectedly" (a 500 on send-message,
            # not a retry). check_connection turns that into a discard-and-replace
            # inside the pool. Costs one round-trip per checkout, which is noise
            # next to the LLM call it precedes.
            check=AsyncConnectionPool.check_connection,
            # psycopg_pool 3.2+ refuses to auto-open in async contexts to avoid
            # hidden blocking I/O during import — open() must be awaited explicitly.
            open=False,
        )
        await _async_pool.open()
    return _async_pool


async def init_interactive_graph():
    """Async initializer for the chat-surface graph. Call from FastAPI lifespan.

    Caches the resulting graph in a module global so subsequent sync
    `get_interactive_graph()` calls hand back the same instance without
    re-running setup.

    ORCHESTRATOR_ROUTER env flag selects topology:
      - 'v1' (default): supervisor + 5 module spokes (this file).
      - 'v2': single conversational router node (orchestrator/graph_v2.py).

    Stage-1 migration is dark by default — v2 only runs when the flag is
    explicitly set, so a rollback is a one-line env-var change. Auto-mode
    is NOT affected by the flag; get_auto_graph() always uses v1 until
    Stage-1 Phase C migrates it separately.
    """
    global _interactive_graph
    if _interactive_graph is not None:
        return _interactive_graph
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    pool = await _get_async_pool()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()

    if os.getenv("ORCHESTRATOR_ROUTER", "v1").lower() == "v2":
        from orchestrator.graph_v2 import build_graph_v2
        logger.info("interactive graph: using router-agent topology (v2)")
        _interactive_graph = build_graph_v2(checkpointer=saver)
    else:
        _interactive_graph = build_graph(interactive=True, checkpointer=saver)
    return _interactive_graph


def get_interactive_graph():
    """Returns the cached async interactive graph.

    Must be initialized first via `await init_interactive_graph()` — typically
    in the FastAPI lifespan startup. Kept as a sync accessor so call sites
    (chat router, tests monkeypatching the function) don't need to change.
    """
    if _interactive_graph is None:
        raise RuntimeError(
            "Interactive graph not initialized. "
            "Call `await init_interactive_graph()` from app startup first."
        )
    return _interactive_graph


@lru_cache(maxsize=1)
def get_auto_graph():
    """Returns the cached auto-mode graph used by the subprocess entrypoint (__main__.py).

    Subprocess (`python -m orchestrator`) drives the graph with sync .invoke(),
    so the sync PostgresSaver is correct here.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_graph(interactive=False, checkpointer=saver)
