"""LangGraph Studio entrypoint for the deep agent.

Studio's `langgraph dev` server wants a no-arg factory and its own checkpoint
storage, so this hands it an in-memory checkpointer over a throwaway project
directory — the topology (model <-> tools, plus deepagents' middleware) is
identical to production, only the checkpointer and workspace differ.

Replaces orchestrator/studio.py: with the graph layer gone, the deep agent is
the only loop worth stepping through.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# `engine` (agent/tools/research.py's europe_pmc/etc. imports) is not an
# installed package — it only lands on sys.path as a side effect of the api
# process importing an orchestrator.tools module first (m2_literature.py /
# m5_writing.py each self-insert repo root + engine/ at import time), or via
# PYTHONPATH=<repo root> in the deployed systemd unit (scripts/deploy.sh).
# `langgraph dev` spawns a bare process from langgraph.json's `./agent`
# dependency alone — neither of those happens — so without this, importing
# agent.runtime here raises `ModuleNotFoundError: No module named 'engine'`
# before Studio ever gets a graph. Same fix, same reasoning as agent/cli.py's
# standalone entrypoint.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from agent.runtime import build_agent  # noqa: E402


def get_studio_graph():
    """Return a fresh deep agent for `langgraph dev`."""
    workspace = Path(tempfile.mkdtemp(prefix="dothesis-studio-"))
    return build_agent(workspace, checkpointer=MemorySaver())
