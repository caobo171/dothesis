"""
ABOUTME: On-disk cache for paid Gemini calls — grounded web search and generate_content.
ABOUTME: One JSON file per key under ~/.dothesis/gemini_cache (DOTHESIS_CACHE_DIR); atomic writes.

Why: a single thesis run fires ~35 Google-grounded searches and ~15 long
Gemini 3.1 Pro generations. Re-running the same case (e2e tests, a retry
after a transient failure, a regenerate of the same paper) used to pay for
every one of them again. Every process — API worker, engine CLI, tests —
shares this directory, so it also replaces the three cwd-relative
`.citation_cache_orchestrator.json` copies that used to drift apart.

Search answers (grounded web search, per-query citation results) live in the
Postgres table `search_cache` when DATABASE_URL is set — one memo shared by
every worker and host — and fall back to the file cache otherwise. The
generate_content replay cache stays on disk: it is a test/retry convenience,
not shared product state.

Switches (environment):
  DOTHESIS_CACHE_DIR        where to store (default ~/.dothesis/gemini_cache)
  DOTHESIS_SEARCH_CACHE_DB  1/0, default 1  — use the search_cache table when DATABASE_URL is set
  DOTHESIS_GROUNDED_CACHE   1/0, default 1  — cache grounded-search answers
  DOTHESIS_LLM_CACHE        1/0, default 0  — cache generate_content answers
                            (opt-in: replays the identical text for an identical
                            prompt, which is what tests want and what a user
                            pressing "regenerate" does not)
  GROUNDED_SEARCH_MODE      always|fallback|off, default always — when the paid
                            grounded search runs relative to the free APIs
"""

import hashlib
import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DAY = 24 * 60 * 60
TTL_GROUNDED_HIT = 30 * DAY   # a found web source stays valid for a month
TTL_GROUNDED_MISS = 3 * DAY   # "nothing found" is retried after a few days
TTL_LLM = 30 * DAY


def cache_root() -> Path:
    return Path(os.getenv("DOTHESIS_CACHE_DIR") or (Path.home() / ".dothesis" / "gemini_cache"))


def _flag(name: str, default: str) -> bool:
    raw = os.getenv(name)
    value = (default if raw is None else raw).strip().lower()
    return value not in ("", "0", "false", "no", "off")


def grounded_cache_enabled() -> bool:
    return _flag("DOTHESIS_GROUNDED_CACHE", "1")


def llm_cache_enabled() -> bool:
    return _flag("DOTHESIS_LLM_CACHE", "0")


def grounded_search_mode() -> str:
    mode = (os.getenv("GROUNDED_SEARCH_MODE") or "always").strip().lower()
    if mode not in ("always", "fallback", "off"):
        logger.warning("GROUNDED_SEARCH_MODE=%r not recognised; using 'always'", mode)
        return "always"
    return mode


def make_key(*parts: Any) -> str:
    """Stable content hash of the request. Dicts are sorted so config order never matters."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path(kind: str, key: str) -> Path:
    return cache_root() / kind / f"{key}.json"


def cache_get(kind: str, key: str) -> Optional[dict]:
    """Return the stored payload, or None when absent / expired / unreadable."""
    path = _path(kind, key)
    try:
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        ttl = record.get("_ttl") or 0
        if ttl and time.time() - record.get("_cached_at", 0) > ttl:
            return None
        return record.get("payload")
    except Exception as e:  # a corrupt entry is a miss, never an error
        logger.debug("cache read failed for %s/%s: %s", kind, key[:12], e)
        return None


# ---------------------------------------------------------------------------
# search_cache table (api/migrations/versions/20260907_search_cache.py)
# ---------------------------------------------------------------------------

_db_engine = None
_db_unavailable = False


def _db():
    """Lazily build one small SQLAlchemy engine per process; None when there is no DB to use."""
    global _db_engine, _db_unavailable
    if _db_unavailable:
        return None
    if _db_engine is None:
        url = os.getenv("DATABASE_URL") or ""
        if not url or not _flag("DOTHESIS_SEARCH_CACHE_DB", "1"):
            _db_unavailable = True
            return None
        try:
            from sqlalchemy import create_engine
            _db_engine = create_engine(url, future=True, pool_pre_ping=True, pool_size=2, max_overflow=2)
        except Exception as e:
            logger.debug("search_cache DB unavailable (%s); using file cache", e)
            _db_unavailable = True
            return None
    return _db_engine


def search_cache_get(kind: str, key: str) -> Optional[dict]:
    """Stored search answer from the DB (file cache when no DB); None when absent or expired."""
    eng = _db()
    if eng is None:
        return cache_get(kind, key)
    try:
        from sqlalchemy import text
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT payload FROM search_cache WHERE key = :k AND expires_at > now()"),
                {"k": key},
            ).first()
        return row[0] if row is not None else None
    except Exception as e:
        logger.debug("search_cache read failed (%s); trying file cache", e)
        return cache_get(kind, key)


def search_cache_put(kind: str, key: str, query: str, model: str, payload: dict, ttl_s: int) -> None:
    """Upsert a search answer; `payload` should carry a null inner result for a remembered miss."""
    eng = _db()
    if eng is None:
        return cache_put(kind, key, payload, ttl_s)
    try:
        from sqlalchemy import text
        hit = any(v for k, v in payload.items() if k in ("result", "results"))
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO search_cache (key, kind, model, query, payload, hit, created_at, expires_at) "
                    "VALUES (:key, :kind, :model, :query, CAST(:payload AS jsonb), :hit, now(), "
                    "        now() + make_interval(secs => :ttl)) "
                    "ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, hit = EXCLUDED.hit, "
                    "  model = EXCLUDED.model, created_at = now(), expires_at = EXCLUDED.expires_at"
                ),
                {"key": key, "kind": kind, "model": (model or "")[:64], "query": (query or "")[:2000],
                 "payload": json.dumps(payload, ensure_ascii=False), "hit": hit, "ttl": int(ttl_s)},
            )
            if random.random() < 0.02:  # opportunistic sweep; nothing reads expired rows anyway
                conn.execute(text("DELETE FROM search_cache WHERE expires_at < now() - interval '7 days'"))
    except Exception as e:
        logger.debug("search_cache write failed (%s); using file cache", e)
        cache_put(kind, key, payload, ttl_s)


def cache_put(kind: str, key: str, payload: dict, ttl_s: Optional[int] = None) -> None:
    """Write atomically (temp file + rename) so parallel workers never see a half-written entry."""
    path = _path(kind, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"_cached_at": time.time(), "_ttl": ttl_s, "_kind": kind, "payload": payload}
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.debug("cache write failed for %s/%s: %s", kind, key[:12], e)
