"""Auto-generate a human-readable thread name (cost-aware).

Threads are born named "Main" / "New thread" / "Start at <artifact>", so a
project list shows a wall of identical "Main" rows. This names a thread ONCE,
cheaply, with a two-tier strategy:

  Tier 1 (free): derive from the M1 research_title the agent already produced —
    the thesis topic IS the natural thread name, zero extra tokens.
  Tier 2 (cheap, fallback): if there's no research_title yet (early M1 or a
    branch thread), one flash-lite call summarizing the first user message.

Guards: runs only when the name is still a default AND name_auto is False, then
sets name_auto=True so it never re-runs and never overwrites a hand-set name.
Scheduled off the response path (background thread) so it never adds turn latency.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid

from sqlalchemy.orm import Session

from .models import ContextStore, Project, Thread

logger = logging.getLogger(__name__)

# Keep references to fire-and-forget tasks so they aren't GC'd mid-flight.
_BG_TASKS: set[asyncio.Task] = set()

_DEFAULT_EXACT = {"main", "new thread"}


def _is_default_name(name: str | None) -> bool:
    n = (name or "").strip().lower()
    return n in _DEFAULT_EXACT or n.startswith("start at ")


def _shorten(title: str, *, max_words: int = 8, max_chars: int = 60) -> str:
    """Trim a title to a compact thread label."""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    # Drop a leading "A study of / An investigation into" style preamble? Keep
    # simple: just trim length. Strip surrounding quotes the LLM sometimes adds.
    t = t.strip('"“”\'')
    words = t.split(" ")
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    if len(t) > max_chars:
        t = t[:max_chars].rstrip()
    return t.rstrip(" .,:;—-")


def _from_research_title(db: Session, project_id: uuid.UUID) -> str | None:
    cs = db.get(ContextStore, project_id)
    m1 = cs.m1_topic if cs else None
    if not isinstance(m1, dict):
        return None
    title = m1.get("research_title") or m1.get("title")
    if isinstance(title, str) and title.strip():
        return _shorten(title)
    return None


def _from_llm(first_user_text: str | None) -> str | None:
    text = (first_user_text or "").strip()
    if not text:
        return None
    try:
        from orchestrator.llm import get_orchestrator_llm
        from orchestrator.message_utils import text_of

        # Route through the shared factory so thread-naming follows the configured
        # provider (native Gemini or Ofox). A hardcoded ChatGoogleGenerativeAI
        # crashes when DOTHESIS_MODEL_ROUTE=ofox (no Google key) — found by the
        # live E2E tier. Naming is a tiny call, so the route's default model is fine.
        llm = get_orchestrator_llm(
            temperature=0.2,
            timeout=int(os.getenv("THREAD_NAMER_TIMEOUT", "12")),
        )
        prompt = (
            "Summarize the following message into a 3–6 word title for a thesis "
            "chat thread. Use the same language as the message. Title Case, no "
            "quotes, no trailing punctuation, no 'Thesis about' preamble.\n\n"
            f"Message:\n{text[:1500]}\n\nTitle:"
        )
        out = text_of(llm.invoke(prompt))
        out = _shorten(out, max_words=6)
        return out or None
    except Exception:  # noqa: BLE001 — naming is best-effort, never raise
        logger.exception("thread auto-name LLM call failed")
        return None


def maybe_autoname_thread(
    engine, thread_id: uuid.UUID, first_user_text: str | None
) -> None:
    """Synchronous core: name the thread if eligible. Safe to call in a worker."""
    try:
        with Session(engine) as db:
            t = db.get(Thread, thread_id)
            if t is None or t.name_auto or not _is_default_name(t.name):
                return
            name = _from_research_title(db, t.project_id) or _from_llm(first_user_text)
            if not name:
                return
            t.name = name
            t.name_auto = True
            db.commit()
            logger.info("auto-named thread %s -> %r", thread_id, name)
    except Exception:  # noqa: BLE001
        logger.exception("thread auto-name failed for %s", thread_id)


def schedule_autoname(engine, thread_id: uuid.UUID, first_user_text: str | None) -> None:
    """Fire-and-forget from an async context — runs the namer in a worker thread
    so it never blocks the SSE response. No-op (logged) if there's no loop."""
    try:
        task = asyncio.create_task(
            asyncio.to_thread(maybe_autoname_thread, engine, thread_id, first_user_text)
        )
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except RuntimeError:
        # No running loop (e.g. called from sync test) — run inline.
        maybe_autoname_thread(engine, thread_id, first_user_text)


# ---------------------------------------------------------------------------
# Project naming — same two-tier strategy as threads, applied to the project
# title that shows in the sidebar / dashboard. Projects are born "Untitled
# thesis" (the drop-first /new page), so without this the list is a wall of
# identical rows. There is no `name_auto` column on Project: the "still a
# default name" check is enough to stop re-runs (once a real name lands it no
# longer matches a default), and it never overwrites a user-set name.
# ---------------------------------------------------------------------------

_DEFAULT_PROJECT_NAMES = {"untitled thesis", "untitled", "new thesis", ""}


def _is_default_project_name(name: str | None) -> bool:
    return (name or "").strip().lower() in _DEFAULT_PROJECT_NAMES


def _project_name_from_llm(first_user_text: str | None) -> str | None:
    text = (first_user_text or "").strip()
    if not text:
        return None
    try:
        from orchestrator.llm import get_orchestrator_llm
        from orchestrator.message_utils import text_of

        # Route through the shared factory (see _from_llm) so project-naming
        # follows the configured provider (native/Ofox) instead of a hardcoded
        # Google client.
        llm = get_orchestrator_llm(
            temperature=0.2,
            timeout=int(os.getenv("PROJECT_NAMER_TIMEOUT", "12")),
        )
        prompt = (
            "Summarize the following into a 3–6 word title for a thesis research "
            "PROJECT (the topic under study). Use the same language as the "
            "message. Title Case, no quotes, no trailing punctuation, no 'Thesis "
            "about' preamble.\n\n"
            f"Message:\n{text[:1500]}\n\nTitle:"
        )
        out = text_of(llm.invoke(prompt))
        return _shorten(out, max_words=6) or None
    except Exception:  # noqa: BLE001 — naming is best-effort, never raise
        logger.exception("project auto-name LLM call failed")
        return None


def maybe_autoname_project(
    engine, project_id: uuid.UUID, first_user_text: str | None
) -> None:
    """Synchronous core: name the project if it's still a default. Worker-safe."""
    try:
        with Session(engine) as db:
            p = db.get(Project, project_id)
            if p is None or not _is_default_project_name(p.name):
                return
            # The drop-first first turn is `/bootstrap` boilerplate, a poor name
            # source — skip the LLM tier for it and rely on the detected
            # research_title (Tier 1). A later real user message names it via
            # the LLM tier if no title was committed.
            text_for_llm = (
                None if (first_user_text or "").lstrip().startswith("/bootstrap")
                else first_user_text
            )
            name = _from_research_title(db, project_id) or _project_name_from_llm(text_for_llm)
            if not name:
                return
            p.name = name
            db.commit()
            logger.info("auto-named project %s -> %r", project_id, name)
    except Exception:  # noqa: BLE001
        logger.exception("project auto-name failed for %s", project_id)


def schedule_autoname_project(
    engine, project_id: uuid.UUID, first_user_text: str | None
) -> None:
    """Fire-and-forget project namer — same worker-thread pattern as threads."""
    try:
        task = asyncio.create_task(
            asyncio.to_thread(maybe_autoname_project, engine, project_id, first_user_text)
        )
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except RuntimeError:
        maybe_autoname_project(engine, project_id, first_user_text)
