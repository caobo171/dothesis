"""v3 chat turn — the deep agent behind the same SSE contract.

When DOTHESIS_AGENT_V3=1, send_message delegates here instead of the
graph_v2 path. Same event vocabulary the web already renders (token /
progress / error / done), same persistence (assistant Message row), same
state sync — except sync is built-in: the agent's commit_slice writes the
context_store/module_status/focus rows directly through DbProjectStateStore,
so there is no end-of-turn copy step.

Tool activity is forwarded as `progress` events, which the frontend already
renders as the live ProgressBubble — the user watches the agent read skills
and call tools in real time (the PDF session's trust-building beat).
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..models import Message, Thread
from ..sse import sse_pack

logger = logging.getLogger(__name__)

# One agent per project per process. Tools close over the project's store and
# workspace, so the cache key is the project id; the checkpointer inside is
# shared (thread_id scopes conversations).
_agents: dict[uuid.UUID, object] = {}
_checkpointer = None


async def _get_checkpointer():
    """AsyncPostgresSaver over the orchestrator's shared async pool.

    Reuses orchestrator.graph's pool so the api process keeps one Postgres
    pool regardless of which brain (graph or agent) serves a project.
    """
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from orchestrator.graph import _get_async_pool
        pool = await _get_async_pool()
        _checkpointer = AsyncPostgresSaver(pool)
        await _checkpointer.setup()
    return _checkpointer


def _workspace_dir(project_id: uuid.UUID) -> Path:
    root = os.getenv("JOB_WORKDIR_ROOT") or tempfile.gettempdir()
    return Path(root) / "agent_projects" / str(project_id)


async def _get_agent(db: Session, project_id: uuid.UUID):
    if project_id in _agents:
        return _agents[project_id]
    from agent.runtime import build_agent
    from ..agent_state import DbProjectStateStore

    store = DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))
    agent = build_agent(
        _workspace_dir(project_id),
        checkpointer=await _get_checkpointer(),
        store=store,
    )
    _agents[project_id] = agent
    return agent


async def send_message_v3(t: Thread, text: str, db: Session) -> StreamingResponse:
    """Persist the user message, run one agent turn, stream SSE."""
    db.add(Message(thread_id=t.id, role="user", content=text))
    db.commit()

    agent = await _get_agent(db, t.project_id)
    # Distinct checkpoint namespace from the graph_v2 thread — the two
    # runtimes have incompatible state channels, and a rollback to the old
    # path must find its own checkpoints untouched.
    agent_thread_id = f"v3:{t.langgraph_thread_id}"

    from agent.runtime import stream_turn
    from ..agent_state import DbProjectStateStore

    engine = db.bind
    project_id = t.project_id
    thread_pk = t.id
    langgraph_thread_id = t.langgraph_thread_id

    async def gen():
        chunks: list[str] = []

        # Engine progress beats (research_scout's 30–90s search) reach the
        # SSE stream through the same registry the graph path used.
        import asyncio as _asyncio
        events_q: _asyncio.Queue = _asyncio.Queue()
        loop = _asyncio.get_running_loop()

        def progress_emitter(payload: dict) -> None:
            # Diagnostic stderr beat — same as the v2 chat router. Tells us
            # whether engine progress is reaching the v3 SSE pipe.
            import sys as _sys
            print(f"[v3-emitter] stage={payload.get('stage')!r} msg={payload.get('message','')[:80]!r}",
                  file=_sys.stderr, flush=True)
            try:
                # Tag the payload as a "progress" event in the multiplexed
                # queue so the consumer can distinguish it from agent
                # events arriving from the pump task.
                loop.call_soon_threadsafe(
                    events_q.put_nowait, ("progress", payload))
            except Exception:  # noqa: BLE001
                pass

        from engine.utils import progress as _engine_progress
        _engine_progress.register(langgraph_thread_id, progress_emitter)
        # Diagnostic counters so a single line at end of turn tells us how
        # many of each event type fired — quick read whether the agent
        # streamed nothing, only tokens, or only tool events.
        _counts = {"token": 0, "tool_start": 0, "tool_end": 0, "error": 0,
                   "done": 0, "engine_progress": 0}
        import sys as _sys
        print(f"[v3] turn start thread={langgraph_thread_id} text={text[:60]!r}",
              file=_sys.stderr, flush=True)
        # Bind the progress emitter as the active ContextVar for the
        # duration of the agent turn. Why: the registry path
        # (`register(thread_id, …)`) is for callers that have the thread_id
        # in hand — M2Agent.step does. But research_scout has no thread_id
        # to look up with; the engine's `safe_print → _safe_print_hook →
        # current_emitter()` chain reads from the ContextVar (PEP 567), not
        # the registry. Binding here means asyncio.to_thread workers and
        # the engine's `submit_with_context`-wrapped ThreadPoolExecutor
        # batches all inherit the emitter — no per-tool plumbing needed.
        # Sync `with` over `async for` is fine: the ContextVar token is
        # held by this frame across every await yield.
        try:
            _bind_ctx = _engine_progress.bind(progress_emitter)
        except Exception:  # noqa: BLE001 — never let progress break a turn
            _bind_ctx = None
        async def _pump_agent():
            """Drain stream_turn into the shared queue. A sentinel marks
            completion so the consumer below can exit cleanly even if the
            agent finishes silently."""
            try:
                async for ev in stream_turn(agent, agent_thread_id, text):
                    await events_q.put(("agent", ev))
            finally:
                await events_q.put(("done", None))

        try:
            if _bind_ctx is not None:
                _bind_ctx.__enter__()
            # MULTIPLEX: previously this loop did `async for ev in
            # stream_turn(...)` and drained engine progress only at the top
            # of the loop body — so while the agent blocked on a 60-90s
            # tool call (research_scout), the body never executed and engine
            # progress events sat in the queue, invisible to the UI. The
            # pump task runs stream_turn in parallel and writes to the same
            # queue the engine writes to; the consumer below yields events
            # the moment EITHER producer puts one. This is the same pattern
            # the v2 chat router uses (chat.py:537-557).
            pump_task = _asyncio.create_task(_pump_agent())

            while True:
                src, item = await events_q.get()
                if src == "done":
                    break
                if src == "progress":
                    # Engine progress beat — forward in real time.
                    _counts["engine_progress"] += 1
                    print(f"[v3-yield] progress #{_counts['engine_progress']} stage={item.get('stage')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "progress", "payload": item})
                    continue
                # src == "agent"
                ev = item
                kind = ev["type"]
                _counts[kind] = _counts.get(kind, 0) + 1
                if kind == "token":
                    chunks.append(ev["text"])
                    yield sse_pack({"type": "token", "module": None, "text": ev["text"]})
                elif kind == "tool_start":
                    print(f"[v3] tool_start name={ev.get('name')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "progress", "payload": {
                        "stage": ev["name"], "message": f"⚙ {ev['name']}…",
                    }})
                elif kind == "tool_end":
                    print(f"[v3] tool_end name={ev.get('name')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "progress", "payload": {
                        "stage": ev["name"], "message": f"✓ {ev['name']}",
                    }})
                elif kind == "error":
                    logger.error("agent turn error for thread %s: %s", thread_pk, ev["message"])
                    print(f"[v3] ERROR msg={ev.get('message')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "error", "message": ev["message"]})
                elif kind == "done":
                    break
            # Re-raise any exception the pump task captured.
            await pump_task
        except Exception as _e:
            # If stream_turn raises outside its own try (or the for loop
            # itself dies), the user gets a silent stream end. Surface it.
            import traceback as _tb
            print(f"\n=== chat_v3 stream crashed for thread {thread_pk} ===",
                  file=_sys.stderr, flush=True)
            _tb.print_exc(file=_sys.stderr)
            print("=== end traceback ===\n", file=_sys.stderr, flush=True)
            yield sse_pack({"type": "error",
                            "message": f"{type(_e).__name__}: {_e}"})
        finally:
            if _bind_ctx is not None:
                try:
                    _bind_ctx.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
            _engine_progress.unregister(langgraph_thread_id)
            print(f"[v3] turn done counts={_counts}",
                  file=_sys.stderr, flush=True)

        # Persist the assistant reply, tagged with the post-turn focus so
        # bubbles get their module chip on reload.
        full = "".join(chunks)
        if full:
            focus = DbProjectStateStore(
                engine, project_id, _workspace_dir(project_id)
            ).load()["focus"]
            with engine.connect() as conn:
                conn.execute(Message.__table__.insert().values(
                    thread_id=thread_pk, role="assistant",
                    content=full, module_tag=focus,
                ))
                conn.commit()
        yield sse_pack({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
