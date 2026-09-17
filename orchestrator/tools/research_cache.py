"""Small, process-safe persistent cache for costly research operations.

The cache deliberately stores only JSON values.  Research callers should treat a
cache failure as an availability concern, never as a reason to repeat the work
inside the same call.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable, TypeVar

from orchestrator.llm import resolve_orchestrator_model


CACHE_VERSION = 1
DEFAULT_TTL_S = 7 * 24 * 60 * 60
MAX_ENTRIES = 2048
MAX_ENTRY_BYTES = 1024 * 1024
LOCK_STRIPES = 64

T = TypeVar("T")
_MISS = object()
_LOCAL_STRIPE_LOCKS = [threading.Lock() for _ in range(LOCK_STRIPES)]


def _cache_dir() -> Path:
    configured = os.environ.get("DOTHESIS_RESEARCH_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "var" / "cache" / "research"


def _normalise(value: Any) -> Any:
    """Make ordinary query parameters stable regardless of mapping order."""
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalise(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _digest(namespace: str, key: Any) -> str:
    payload = {"cache_version": CACHE_VERSION, "namespace": namespace, "key": _normalise(key)}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prepare(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Decision: ensure a pre-existing cache directory does not widen access.
    directory.chmod(0o700)


def _read(path: Path, now: float, ttl_s: float) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        if (not isinstance(record, dict) or record.get("cache_version") != CACHE_VERSION or
                not isinstance(record.get("expires_at"), (int, float)) or
                now > record["expires_at"] or "value" not in record):
            return _MISS
        return copy.deepcopy(record["value"])
    except (OSError, ValueError, TypeError, KeyError):
        # A partially written/corrupt cache is just a miss; the atomic writer
        # ensures healthy readers do not observe a normal in-progress write.
        return _MISS


def model_cache_key(prompt: str, *, model: str | None = None, route: str | None = None,
                    temperature: float = 0.4) -> dict[str, Any]:
    """Build a non-secret, model-sensitive key for validated LLM outputs.

    Callers pass this complete dictionary as ``key`` to :func:`cached_call`
    only after their parser/validator has accepted the model result.  The full
    prompt is intentional: a prompt instruction change must invalidate prior
    output.  Endpoint values are fingerprinted, never retained in cache files,
    because custom gateway URLs can themselves contain credentials.
    """
    selected_route = (route or os.getenv("ORCHESTRATOR_LLM_ROUTE", "openai")).lower()
    selected_model = model or resolve_orchestrator_model()
    endpoint_names = {
        "openai": ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_ENDPOINT"),
        "ofox": ("OFOX_BASE_URL",),
        "native": ("GOOGLE_GENAI_BASE_URL", "GOOGLE_API_BASE", "GEMINI_API_BASE"),
    }
    endpoint = next((os.getenv(name) for name in endpoint_names.get(selected_route, ()) if os.getenv(name)), "")
    return {
        "cache_version": CACHE_VERSION,
        "kind": "validated-llm-output",
        "route": selected_route,
        "model": selected_model,
        "temperature": temperature,
        "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        "prompt": prompt,
    }


def _acquire_lock(path: Path, wait_s: float):
    """Return an open, exclusively locked handle or ``None`` after the bound."""
    deadline = time.monotonic() + max(0.0, wait_s)
    try:
        stripe = int(path.stem.rsplit("-", 1)[-1])
    except ValueError:
        stripe = 0
    local_lock = _LOCAL_STRIPE_LOCKS[stripe % LOCK_STRIPES]
    if not local_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise TimeoutError("research cache key is still being computed")
    try:
        handle = path.open("a+")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        local_lock.release()
        return None
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle, local_lock
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                local_lock.release()
                # A second expensive request is worse than a visible retry:
                # callers must never silently duplicate paid model/provider work.
                raise TimeoutError("research cache key is still being computed")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        except OSError:
            handle.close()
            local_lock.release()
            return None


def _write(path: Path, record: dict[str, Any]) -> bool:
    try:
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_ENTRY_BYTES:
            return False
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded.decode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            return True
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    except (OSError, TypeError, ValueError):
        return False


def _prune(directory: Path, now: float) -> None:
    """Bound disk use; failures are intentionally non-fatal cache misses."""
    try:
        entries = [entry for entry in directory.glob("*.json") if entry.is_file()]
        expired = []
        live = []
        for entry in entries:
            try:
                with entry.open("r", encoding="utf-8") as handle:
                    record = json.load(handle)
                if not isinstance(record, dict) or not isinstance(record.get("expires_at"), (int, float)) or now > record["expires_at"]:
                    expired.append(entry)
                else:
                    live.append(entry)
            except (OSError, ValueError, TypeError):
                continue
        for entry in expired:
            try:
                entry.unlink()
            except OSError:
                pass
        if len(live) > MAX_ENTRIES:
            for entry in sorted(live, key=lambda item: item.stat().st_mtime)[:len(live) - MAX_ENTRIES]:
                try:
                    entry.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def store_completed_result(namespace: str, key: Any, value: Any, *, ttl_s: float = DEFAULT_TTL_S) -> None:
    """Publish an already validated late response without taking its caller's lock.

    The miss coordinator may still hold that lock while waiting on this worker.
    Atomic replacement keeps readers safe; this function never computes or pays.
    """
    try:
        directory = _cache_dir()
        _prepare(directory)
        now = time.time()
        path = directory / f"{_digest(namespace, key)}.json"
        _write(path, {"cache_version": CACHE_VERSION, "created_at": now,
                      "expires_at": now + ttl_s, "value": value})
        _prune(directory, now)
    except (OSError, ValueError, TypeError):
        pass


def cached_call(namespace: str, key: Any, compute: Callable[[], T], *, ttl_s: float = DEFAULT_TTL_S,
                cache_if: Callable[[T], bool] | None = None, wait_s: float = 20) -> T:
    """Return a cached JSON result or calculate it once while peers wait.

    ``cache_if`` lets callers avoid retaining failed/empty provider responses.
    Exceptions from ``compute`` always propagate and are never written.
    """
    ttl_s = max(0.0, ttl_s)
    digest = _digest(namespace, key)
    try:
        directory = _cache_dir()
        _prepare(directory)
        value_path = directory / f"{digest}.json"
        cached = _read(value_path, time.time(), ttl_s)
        if cached is not _MISS:
            return cached
        # 64 stripes cap lock artifacts while re-checking after acquisition
        # still prevents duplicate work for identical keys in normal operation.
        lock_path = directory / f"lock-{int(digest[:8], 16) % LOCK_STRIPES:02d}.lock"
        lock_info = _acquire_lock(lock_path, wait_s)
    except TimeoutError:
        # TimeoutError is an OSError subclass; keep it distinct so contention
        # cannot silently turn into a second paid request.
        raise
    except (OSError, ValueError):
        lock_info = None
        value_path = None

    if lock_info is not None:
        lock, local_lock = lock_info
        try:
            cached = _read(value_path, time.time(), ttl_s)  # type: ignore[arg-type]
            if cached is not _MISS:
                return cached
            result = compute()
            should_cache = True if cache_if is None else bool(cache_if(result))
            if should_cache:
                # Do not call compute again when disk serialization/write fails.
                created_at = time.time()
                _write(value_path, {"cache_version": CACHE_VERSION, "created_at": created_at,
                                    "expires_at": created_at + ttl_s, "value": result})  # type: ignore[arg-type]
                _prune(value_path.parent, created_at)  # type: ignore[union-attr]
            return copy.deepcopy(result)
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()
                local_lock.release()

    # Cache I/O failure must not make research unavailable.  A
    # single invocation computes exactly once even when its eventual write fails.
    return copy.deepcopy(compute())
