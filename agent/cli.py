"""CLI spike for the v3 deep agent — migration step 1.

Chat with the skills-driven agent against a throwaway project directory:

    api/.venv/bin/python -m agent.cli --project /tmp/thesis-spike
    api/.venv/bin/python -m agent.cli --project /tmp/thesis-spike --once "hello"

The CLI consumes the same event stream the web SSE endpoint will (stream_turn),
so what you see here — tokens, tool activity, errors — is exactly what the
frontend will receive.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Repo root on sys.path so `agent`, `orchestrator`, `engine` all import when
# run as `python -m agent.cli` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DIM = "\033[2m"
CYAN = "\033[36m"
RED = "\033[31m"
RESET = "\033[0m"


async def run_turn(agent, thread_id: str, text: str, store=None) -> None:
    from agent.runtime import stream_turn

    async for ev in stream_turn(agent, thread_id, text, store=store):
        kind = ev["type"]
        if kind == "token":
            print(ev["text"], end="", flush=True)
        elif kind == "tool_start":
            print(f"\n{CYAN}⚙ {ev['name']}{RESET} {DIM}{_short(ev['args'])}{RESET}", flush=True)
        elif kind == "tool_end":
            print(f"{DIM}  ↳ {ev['preview']}{RESET}", flush=True)
        elif kind == "error":
            print(f"\n{RED}✖ {ev['message']}{RESET}", flush=True)
        elif kind == "done":
            print(flush=True)


def _short(args: dict, limit: int = 120) -> str:
    s = str(args)
    return s[:limit] + ("…" if len(s) > limit else "")


async def main() -> None:
    parser = argparse.ArgumentParser(description="DoThesis deep-agent CLI spike")
    parser.add_argument("--project", required=True, help="project directory (state + uploads)")
    parser.add_argument("--thread", default=None, help="thread id (default: new)")
    parser.add_argument("--once", default=None, help="send one message and exit")
    args = parser.parse_args()

    from langgraph.checkpoint.memory import InMemorySaver

    from agent.runtime import build_agent

    # InMemorySaver = conversation lives for the process; the context_store
    # persists in the project dir regardless (project-scoped, thread-agnostic).
    agent = build_agent(args.project, checkpointer=InMemorySaver())
    # File-backed store over the same project dir — feeds the authoritative
    # [PROJECT STATE] header into each turn (same store the agent commits to).
    from agent.state import ProjectStateStore
    store = ProjectStateStore(args.project)
    thread_id = args.thread or f"cli-{uuid.uuid4().hex[:8]}"
    print(f"{DIM}project={args.project} thread={thread_id} — Ctrl-D to exit{RESET}")

    if args.once:
        await run_turn(agent, thread_id, args.once, store=store)
        return

    while True:
        try:
            text = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        await run_turn(agent, thread_id, text, store=store)


if __name__ == "__main__":
    asyncio.run(main())
