import json
import multiprocessing
import os
import stat
import threading
import time

import pytest

from orchestrator.tools import research_cache


def _cross_process_cache_worker(start, calls, results):
    start.wait(2)

    def compute():
        with calls.get_lock():
            calls.value += 1
        time.sleep(.1)
        return {"value": "shared"}

    results.put(research_cache.cached_call("cross-process", {"q": "trust"}, compute, wait_s=2))


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    root = tmp_path / "research-cache"
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(root))
    return root


def test_persists_across_calls_and_returns_deep_copies(cache_dir):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"papers": [{"title": "One"}]}

    first = research_cache.cached_call("openalex", {"query": "trust", "page": 1}, compute)
    first["papers"][0]["title"] = "mutated"
    second = research_cache.cached_call("openalex", {"page": 1, "query": "trust"}, compute)
    assert calls == 1
    assert second == {"papers": [{"title": "One"}]}
    assert stat.S_IMODE(cache_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in cache_dir.glob("*.json"))


def test_ttl_and_errors_are_not_cached(cache_dir, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(research_cache.time, "time", lambda: now[0])
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"call": calls}

    assert research_cache.cached_call("x", "key", compute, ttl_s=10) == {"call": 1}
    now[0] += 11
    assert research_cache.cached_call("x", "key", compute, ttl_s=10) == {"call": 2}

    failures = 0
    def failing():
        nonlocal failures
        failures += 1
        raise RuntimeError("retry")
    with pytest.raises(RuntimeError):
        research_cache.cached_call("x", "error", failing)
    with pytest.raises(RuntimeError):
        research_cache.cached_call("x", "error", failing)
    assert failures == 2


def test_corrupt_records_and_incompatible_parameters_miss(cache_dir):
    calls = 0
    def compute():
        nonlocal calls
        calls += 1
        return {"call": calls}

    assert research_cache.cached_call("crossref", {"query": "trust", "rows": 10}, compute) == {"call": 1}
    cache_file = next(cache_dir.glob("*.json"))
    cache_file.write_text("not json", encoding="utf-8")
    assert research_cache.cached_call("crossref", {"query": "trust", "rows": 10}, compute) == {"call": 2}
    assert research_cache.cached_call("crossref", {"query": "trust", "rows": 20}, compute) == {"call": 3}
    cache_file.write_text("[]", encoding="utf-8")
    assert research_cache.cached_call("crossref", {"query": "trust", "rows": 10}, compute) == {"call": 4}


def test_cache_if_and_write_failure_never_repeat_one_invocation(cache_dir, monkeypatch):
    calls = 0
    def compute():
        nonlocal calls
        calls += 1
        return {"papers": []}

    research_cache.cached_call("search", "empty", compute, cache_if=lambda result: bool(result["papers"]))
    research_cache.cached_call("search", "empty", compute, cache_if=lambda result: bool(result["papers"]))
    assert calls == 2

    monkeypatch.setattr(research_cache.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    assert research_cache.cached_call("search", "write-failure", compute) == {"papers": []}
    assert calls == 3


def test_parallel_same_key_computes_once(cache_dir):
    calls = 0
    calls_lock = threading.Lock()
    barrier = threading.Barrier(4)
    results = []

    def compute():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(.1)
        return {"value": "shared"}

    def worker():
        barrier.wait()
        results.append(research_cache.cached_call("semantic", {"q": "trust"}, compute, wait_s=2))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert results == [{"value": "shared"}] * 4


def test_cross_process_same_key_computes_once(cache_dir):
    # flock is the process boundary; this is intentionally not a thread-only test.
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    calls = context.Value("i", 0)
    results = context.Queue()
    workers = [context.Process(target=_cross_process_cache_worker, args=(started, calls, results)) for _ in range(2)]
    for worker in workers:
        worker.start()
    started.set()
    for worker in workers:
        worker.join(3)
        assert worker.exitcode == 0
    assert calls.value == 1
    assert [results.get(timeout=1) for _ in workers] == [{"value": "shared"}] * 2


def test_model_cache_key_changes_for_full_prompt_and_nonsecret_endpoint(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "openai")
    monkeypatch.setenv("ORCHESTRATOR_LLM_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1?token=secret")
    first = research_cache.model_cache_key("full prompt A")
    second = research_cache.model_cache_key("full prompt B")
    assert first["route"] == "openai" and first["model"] == "test-model"
    assert first["temperature"] == .4
    assert first["endpoint_sha256"] != "https://gateway.example/v1?token=secret"
    assert first != second


def test_mixed_ttls_keep_long_identity_entry_and_oversized_values_are_not_cached(cache_dir, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(research_cache.time, "time", lambda: now[0])
    long_calls = 0
    def identity():
        nonlocal long_calls
        long_calls += 1
        return {"identity": "resolved"}
    research_cache.cached_call("identity", "doi", identity, ttl_s=30 * 24 * 60 * 60)
    now[0] += 8 * 24 * 60 * 60
    research_cache.cached_call("llm", "prompt", lambda: {"ok": True}, ttl_s=7 * 24 * 60 * 60)
    assert research_cache.cached_call("identity", "doi", identity, ttl_s=30 * 24 * 60 * 60) == {"identity": "resolved"}
    assert long_calls == 1

    enormous_calls = 0
    def enormous():
        nonlocal enormous_calls
        enormous_calls += 1
        return {"text": "x" * (research_cache.MAX_ENTRY_BYTES + 1)}
    research_cache.cached_call("search", "large", enormous)
    research_cache.cached_call("search", "large", enormous)
    assert enormous_calls == 2


def test_lock_timeout_does_not_duplicate_expensive_compute(cache_dir):
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def slow():
        nonlocal calls
        calls += 1
        started.set()
        release.wait(2)
        return {"ok": True}

    first = threading.Thread(target=lambda: research_cache.cached_call("llm", "same", slow, wait_s=2))
    first.start()
    assert started.wait(1)
    with pytest.raises(TimeoutError):
        research_cache.cached_call("llm", "same", slow, wait_s=.01)
    release.set()
    first.join()
    assert calls == 1


def test_cache_survives_a_fresh_python_process(cache_dir):
    import subprocess
    import sys
    first = "from orchestrator.tools.research_cache import cached_call; print(cached_call('restart','same',lambda: {'papers': 3}))"
    second = "from orchestrator.tools.research_cache import cached_call\ndef forbidden(): raise AssertionError('charged twice')\nprint(cached_call('restart','same',forbidden))"
    a=subprocess.run([sys.executable,'-c',first],check=True,capture_output=True,text=True)
    b=subprocess.run([sys.executable,'-c',second],check=True,capture_output=True,text=True)
    assert a.stdout==b.stdout and "'papers': 3" in b.stdout
