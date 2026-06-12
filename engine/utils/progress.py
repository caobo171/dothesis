"""Progress emitter — surfaces engine activity (safe_print lines) to outside listeners.

The engine prints rich progress to stdout while running the citation
research pipeline (Crossref / OpenAlex / Semantic Scholar / Gemini chains,
per-topic queries, parallel batch status). Useful for terminal debugging,
but invisible to the chat user who just sees a typing dot during M2's
30-60s scout.

This module gives the chat router (or any other listener) a way to hook in
and receive those progress lines as structured events, while keeping the
existing stdout prints untouched for terminal/log readers.

## Wiring summary

  chat router  ──── progress.bind(emitter)  ───► engine code
                                                 │
                                                 ▼
                                        safe_print(...) emits
                                                 │
                                                 ▼
                                            emitter(payload)

The emitter is stored in a `threading.local` so each LangGraph executor
thread can have its own. The chat router binds the emitter in the main
asyncio task; M2 phase2 re-binds it inside the executor thread that runs
the actual scout (since `threading.local` does NOT propagate across
threads — see `progress.bind_in_executor`).

Listeners typically wrap a thread-safe queue + an asyncio event loop
reference, using `loop.call_soon_threadsafe(queue.put_nowait, item)` from
the emitter callback to bridge back to async land.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import threading
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)

# Active emitter, scoped to the current execution context.
#
# History: this was a `threading.local` because the old assumption was
# that contextvars don't propagate to executor threads. They DO —
# `concurrent.futures.ThreadPoolExecutor.submit` captures the calling
# context (see PEP 567), and `asyncio.to_thread` does the same. The
# threading.local approach silently dropped events whenever the engine's
# citation-scout spawned worker threads for batched topic lookups: the
# parent thread bound the emitter, the workers ran `safe_print` →
# `_safe_print_hook` → `current_emitter()` and got None, so the per-topic
# `🔍 Researching: …` lines never reached the SSE stream.
#
# ContextVar fixes the scout case (workers inherit) while leaving the
# explicit thread_id-keyed `_registry` below as the durable lookup path
# for code that has no access to the parent context — e.g. M2Agent.step
# running in a LangGraph sync node, which only sees `state["thread_id"]`.
_emitter_cv: contextvars.ContextVar[Optional["EmitterFn"]] = (
    contextvars.ContextVar("progress_emitter", default=None)
)

EmitterFn = Callable[[dict], None]


# Thread-id keyed registry — separate from the per-thread `bind` API.
#
# Why: LangGraph persists graph state to a checkpointer (postgres,
# msgpack-serialized). Putting a Python callable directly into graph state
# crashes with `TypeError: Type is not msgpack serializable: function`.
#
# Solution: the chat router stashes the emitter HERE (keyed by the
# LangGraph thread_id, which IS serializable) and clears it at end of
# request. Module code looks it up by reading `state["thread_id"]` and
# calling `progress.lookup(thread_id)`. Graph state stays clean; the
# emitter never touches the checkpoint.
_registry: dict[str, EmitterFn] = {}
_registry_lock = threading.Lock()


def register(thread_id: str, emitter: EmitterFn) -> None:
    """Bind an emitter to a thread_id for the lifetime of a request.

    Idempotent — repeat registrations overwrite. Call once at the start of
    a streamed request; pair with `unregister` in a finally block so a
    failed request can't leak emitters that point to a closed asyncio loop.
    """
    with _registry_lock:
        _registry[str(thread_id)] = emitter


def unregister(thread_id: str) -> None:
    """Drop the emitter for `thread_id`. Safe to call when no binding
    exists — useful in unconditional `finally` cleanup."""
    with _registry_lock:
        _registry.pop(str(thread_id), None)


def lookup(thread_id: str | None) -> Optional[EmitterFn]:
    """Return the emitter for `thread_id`, or None if no one is listening.

    `None`-safe so callers can do
        emitter = progress.lookup(state.get("thread_id"))
    even on entry paths that never had a thread_id set.
    """
    if thread_id is None:
        return None
    with _registry_lock:
        return _registry.get(str(thread_id))


def current_emitter() -> Optional[EmitterFn]:
    """Return the emitter for the current context, or None if nothing is bound.

    Engine code uses this through `emit()`; direct callers may also poll it
    if they need to know whether progress streaming is active. Backed by a
    ContextVar — propagates across `ThreadPoolExecutor.submit`,
    `asyncio.to_thread`, and any `copy_context().run(...)` boundary.
    """
    return _emitter_cv.get()


def emit(stage: str, message: str, **meta) -> None:
    """Fire a progress event to the currently-bound emitter.

    Best-effort — silently swallows emitter exceptions so engine progress
    never breaks the actual citation work. `stage` is a short category
    label (e.g. 'scout.start', 'scout.api_chain', 'scout.querying'); the
    frontend uses it for icons/coloring. `message` is the human-readable
    line that goes in the progress banner. Extra `meta` is forwarded
    verbatim — handy for fields like `topic`, `api_chain`.
    """
    fn = current_emitter()
    if fn is None:
        return
    try:
        fn({"stage": stage, "message": message, **meta})
    except Exception:  # noqa: BLE001 — progress is best-effort
        logger.exception("progress emitter raised; ignoring")


@contextlib.contextmanager
def bind(emitter: EmitterFn) -> Iterator[None]:
    """Bind `emitter` as the active progress sink for the current context.

    Use as a context manager around the work whose progress you want
    streamed. On exit the previous emitter (if any) is restored.

    Propagation: backed by a ContextVar, so sub-threads spawned via
    `ThreadPoolExecutor.submit` inherit the binding (PEP 567). This means
    the engine's batched citation scout — which runs per-topic lookups on
    worker threads — surfaces every `🔍 Researching: …` line through the
    emitter without each worker having to re-bind.
    """
    token = _emitter_cv.set(emitter)
    try:
        yield
    finally:
        _emitter_cv.reset(token)


@contextlib.contextmanager
def bind_in_executor(emitter: EmitterFn) -> Iterator[None]:
    """Same as `bind`, but explicit about what it's for.

    The chat router runs in an asyncio task on the main thread, but
    LangGraph's sync node functions run in `asyncio.to_thread` executor
    threads. With the ContextVar-backed `bind`, the asyncio task's
    binding propagates into `to_thread` automatically — so calling this
    inside the node body is technically redundant for that hop. It's
    kept as a deliberate re-bind because (a) it documents intent at the
    sync/async boundary and (b) it survives codepaths that explicitly
    drop or reset the parent context.

    Identical behavior to `bind` — separate name just to make the intent
    obvious at call sites that span thread boundaries.
    """
    with bind(emitter):
        yield


def submit_with_context(executor, fn, *args, **kwargs):
    """Submit `fn` to a `concurrent.futures.Executor` carrying the caller's
    ContextVars.

    Why this exists: `ThreadPoolExecutor.submit` does NOT auto-propagate
    contextvars to its worker threads (PEP 567 only mandates that for
    asyncio Tasks). Without this wrapper, the engine's batched citation
    scout submits `_research_single_topic` to a 5-worker pool; the parent
    thread's `progress.bind(...)` binding stays on the parent and every
    worker sees `current_emitter() == None`. Result: the per-topic
    `🔍 Researching: …` lines fall on the floor, the SSE stream goes
    quiet for ~4 min, and the frontend banner stalls.

    Wrapping the call as `ctx.run(fn, *args)` runs `fn` inside a copy of
    the caller's context, so the worker sees the parent's emitter and
    every `safe_print → _safe_print_hook → emit` chain fires.

    Use this everywhere the engine spawns worker threads that should
    surface progress.
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


def _safe_print_hook(args: tuple, end: str) -> None:
    """Side-channel hook fired by engine.utils.api_citations.safe_print.

    Lives here (instead of in the engine module) so the emitter logic
    stays in one place. The print itself still happens; we just shadow
    its content into an emit() call when a listener is bound.

    `end` mirrors print()'s `end` kwarg so a `print("x", end=" ")` followed
    by `print("y")` still reads as `"x y"` to a listener — useful for the
    engine's progressive lines (it prints partial pieces and finishes
    with a check mark).
    """
    if current_emitter() is None:
        return
    text = " ".join(str(a) for a in args).strip()
    if not text:
        return
    # Coarse stage tagging from the engine's emoji prefixes — gives the
    # frontend a hook to pick an icon without parsing message text.
    stage = "engine"
    if "Researching" in text:
        stage = "scout.topic"
    elif "Query type" in text:
        stage = "scout.classify"
    elif "API chain" in text:
        stage = "scout.api_chain"
    elif "Querying" in text or "Trying" in text:
        stage = "scout.querying"
    elif "Processing batch" in text:
        stage = "scout.batch"
    elif text.startswith("✓") or text.startswith("✗"):
        stage = "scout.api_result"
    emit(stage, text.strip())
