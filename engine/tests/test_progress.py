"""Tests for engine.utils.progress — emitter binding + safe_print hook."""
from __future__ import annotations

import threading

import pytest

from engine.utils import progress


def test_emit_is_a_noop_when_no_emitter_bound():
    # No assertion on side-effects — the contract is 'never raises'.
    progress.emit("scout.topic", "ignored")
    assert progress.current_emitter() is None


def test_bind_routes_emit_to_callback():
    received: list[dict] = []
    with progress.bind(received.append):
        progress.emit("scout.topic", "Researching: X", topic="X")
    assert received == [{"stage": "scout.topic", "message": "Researching: X",
                         "topic": "X"}]
    assert progress.current_emitter() is None   # restored on exit


def test_bind_restores_prior_emitter_on_exit():
    outer: list[dict] = []
    inner: list[dict] = []
    with progress.bind(outer.append):
        with progress.bind(inner.append):
            progress.emit("a", "hi")
        progress.emit("b", "bye")
    assert inner == [{"stage": "a", "message": "hi"}]
    assert outer == [{"stage": "b", "message": "bye"}]


def test_bind_is_per_thread_not_inherited_by_spawned_threads():
    """A bare `threading.Thread` does NOT copy contextvars to its target —
    only `ThreadPoolExecutor.submit` and `asyncio.to_thread` do (PEP 567).
    Documenting that boundary: callers that hand-roll a Thread still need
    to re-bind on the other side; the `bind`→ContextVar swap only buys
    automatic propagation for the executor cases."""
    received_main: list[dict] = []
    received_child: list[dict] = []

    def child_no_bind():
        # Should see no emitter — parent's bind doesn't reach us.
        progress.emit("scout.topic", "from-child")
        received_child.append({"saw_emitter": progress.current_emitter() is not None})

    with progress.bind(received_main.append):
        t = threading.Thread(target=child_no_bind)
        t.start()
        t.join()
    assert received_child == [{"saw_emitter": False}]
    assert received_main == []   # child's emit went nowhere


def test_plain_executor_submit_does_not_propagate_emitter():
    """Document the limitation that motivates submit_with_context: a bare
    `ThreadPoolExecutor.submit` does NOT carry ContextVars to its worker
    (PEP 567 only mandates that for asyncio Tasks). If we relied on the
    plain submit, the engine's batched scout would silently drop progress
    even with the ContextVar binding."""
    from concurrent.futures import ThreadPoolExecutor

    received: list[dict] = []

    def worker():
        progress.emit("scout.topic", "worker")
        return progress.current_emitter() is not None

    with progress.bind(received.append):
        with ThreadPoolExecutor(max_workers=1) as ex:
            saw_emitter = ex.submit(worker).result()
    assert saw_emitter is False
    assert received == []


def test_submit_with_context_propagates_emitter_to_workers():
    """The fix path: `progress.submit_with_context(executor, fn)` wraps fn
    with copy_context().run so the worker sees the parent's emitter
    binding. This is the call the engine's batch scout MUST use at every
    executor.submit site that should surface progress."""
    from concurrent.futures import ThreadPoolExecutor

    received: list[dict] = []

    def worker(label: str):
        progress.emit("scout.topic", label)
        return progress.current_emitter() is not None

    with progress.bind(received.append):
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = [progress.submit_with_context(ex, worker, lbl)
                       for lbl in ("a", "b", "c", "d")]
            results = [f.result() for f in futures]
    assert results == [True, True, True, True]
    messages = sorted(p["message"] for p in received)
    assert messages == ["a", "b", "c", "d"]


def test_emitter_exception_is_swallowed():
    """A buggy emitter must not break the engine's actual citation work."""
    def boom(_payload):
        raise RuntimeError("network ded")
    with progress.bind(boom):
        # Must not raise. Just logs and moves on.
        progress.emit("scout.topic", "fine")


def test_safe_print_hook_tags_engine_progress_stages():
    """The hook reads the engine's emoji-prefixed lines and tags them with
    coarse stage labels (scout.topic / scout.api_chain / ...) so the frontend
    can pick an icon without parsing message text."""
    received: list[dict] = []
    with progress.bind(received.append):
        progress._safe_print_hook(("🔍 Researching: Gen z + tiktok",), end="\n")
        progress._safe_print_hook(("📊 Query type: mixed (confidence: 0.30)",), end="\n")
        progress._safe_print_hook(("🔀 API chain: gemini_grounded → crossref",), end="\n")
        progress._safe_print_hook(("→ Trying Gemini Grounded...",), end="\n")
        progress._safe_print_hook(("📦 Processing batch 1 (10 topics)...",), end="\n")
        progress._safe_print_hook(("✓ (Crossref)",), end="\n")

    stages = [r["stage"] for r in received]
    assert stages == [
        "scout.topic", "scout.classify", "scout.api_chain",
        "scout.querying", "scout.batch", "scout.api_result",
    ]


def test_safe_print_hook_skips_when_no_emitter():
    # Sanity: hook shouldn't try to format args when nobody is listening.
    progress._safe_print_hook(("anything",), end="\n")  # must not raise


def test_registry_register_lookup_unregister_roundtrip():
    """P5: the thread-id keyed registry is the path used by graph state —
    callables can't be msgpack-serialized into the LangGraph checkpoint, so
    M2Agent looks up the emitter via this registry by state['thread_id']
    instead of carrying it in state."""
    received: list[dict] = []
    progress.register("thread-A", received.append)

    fn = progress.lookup("thread-A")
    assert fn is not None
    fn({"stage": "x", "message": "hello"})
    assert received == [{"stage": "x", "message": "hello"}]

    # Lookup is uuid/string agnostic — accepts whatever the graph stores.
    assert progress.lookup("thread-B") is None
    assert progress.lookup(None) is None

    progress.unregister("thread-A")
    assert progress.lookup("thread-A") is None
    # Idempotent — unregister twice doesn't raise.
    progress.unregister("thread-A")


def test_registry_concurrent_registrations_dont_collide():
    """Two requests in flight at once must each get their own emitter."""
    a, b = [], []
    progress.register("A", a.append)
    progress.register("B", b.append)
    progress.lookup("A")({"stage": "x", "message": "from-A"})
    progress.lookup("B")({"stage": "x", "message": "from-B"})
    assert a == [{"stage": "x", "message": "from-A"}]
    assert b == [{"stage": "x", "message": "from-B"}]
    progress.unregister("A"); progress.unregister("B")


def test_safe_print_in_orchestrator_fans_out_to_emitter(capsys):
    """End-to-end: when the engine's `safe_print` is called while an emitter
    is bound, the line appears in BOTH stdout AND the emitter. Stdout
    behavior is unchanged — only an extra side channel is added."""
    from engine.utils.api_citations import orchestrator
    # Force verbose mode so safe_print actually writes to stdout.
    orchestrator._verbose_research = True

    received: list[dict] = []
    with progress.bind(received.append):
        orchestrator.safe_print("🔍 Researching: Gen z + tiktok")

    captured = capsys.readouterr()
    assert "Researching" in captured.out
    assert len(received) == 1
    assert received[0]["stage"] == "scout.topic"
    assert "Gen z" in received[0]["message"]


def test_safe_print_hook_skips_empty_strings():
    """The engine often prints a trailing newline or whitespace via end='';
    those shouldn't surface as empty progress events."""
    received: list[dict] = []
    with progress.bind(received.append):
        progress._safe_print_hook(("",), end="")
        progress._safe_print_hook(("   ",), end="")
    # Whitespace-only message strips to empty so the second one IS emitted
    # but the first is dropped — accept either as long as no empty.message
    # gets through.
    for r in received:
        assert r["message"].strip()
