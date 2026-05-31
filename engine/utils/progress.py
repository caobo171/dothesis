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
import logging
import threading
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)

# Per-thread emitter. None when no one is listening; engine code then
# behaves exactly as before (just stdout). This is a `threading.local`
# rather than a contextvar because LangGraph runs sync graph nodes in
# its executor pool, and contextvars don't propagate to executor threads
# without explicit `copy_context().run(...)` plumbing — which we don't
# control.
_state = threading.local()

EmitterFn = Callable[[dict], None]


def current_emitter() -> Optional[EmitterFn]:
    """Return the emitter for this thread, or None if nothing is bound.

    Engine code uses this through `emit()`; direct callers may also poll it
    if they need to know whether progress streaming is active.
    """
    return getattr(_state, "emitter", None)


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
    """Bind `emitter` as the active progress sink for THIS thread only.

    Use as a context manager around the work whose progress you want
    streamed. On exit the previous emitter (if any) is restored.

    Reminder: `threading.local` is per-OS-thread. If the work you wrap
    here spawns sub-threads, those sub-threads will NOT inherit the
    binding. Use `bind_in_executor` from the spawn site if you need
    propagation.
    """
    prev = getattr(_state, "emitter", None)
    _state.emitter = emitter
    try:
        yield
    finally:
        _state.emitter = prev


@contextlib.contextmanager
def bind_in_executor(emitter: EmitterFn) -> Iterator[None]:
    """Same as `bind`, but explicit about what it's for.

    The chat router runs in an asyncio task on the main thread, but
    LangGraph's sync node functions run in `asyncio.to_thread` executor
    threads. Calling `bind` from the main task doesn't help: the engine
    code running in the executor thread sees its own (empty)
    `threading.local`. The fix is to call `bind_in_executor` AT THE
    START of the node function (or wherever sync engine work begins) so
    the binding lives in the right thread.

    Identical behavior to `bind` — separate name just to make the intent
    obvious at call sites that span thread boundaries.
    """
    with bind(emitter):
        yield


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
