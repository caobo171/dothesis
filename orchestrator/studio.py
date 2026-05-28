"""LangGraph Studio entrypoint.

Decision: Studio's `langgraph dev` server compiles its own checkpoint trace
storage and does NOT want a Postgres-backed AsyncSaver — those exist for the
production FastAPI lifespan in `init_interactive_graph()`. We expose a no-arg
sync factory that hands Studio a graph wired to an in-memory checkpointer
instead, so you can visualize/step through the topology without touching the
production DB or needing the FastAPI app to be running.

The graph topology (nodes, edges, interrupt_after points) is identical to the
production interactive graph — only the checkpointer differs.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from orchestrator.graph import build_graph


def get_studio_graph():
    """Return a fresh interactive orchestrator graph for `langgraph dev`."""
    return build_graph(interactive=True, checkpointer=MemorySaver())
