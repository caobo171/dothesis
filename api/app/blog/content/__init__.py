"""DoThesis blog content engine.

Turns measured search demand into seed JSON: `expand` crosses the axis unit
lists with their phrasing templates, `gate` measures the candidates and applies
the cut rules, `plan` merges the survivors with the competitor harvest into a
backlog, `write` calls the model per row, `qa` is the mechanical gate, `report`
counts what came out. `python -m app.blog.content.cli` is the only entry point.

Two deliberate constraints on this package:

  * **Stdlib only at import time.** `qa.py` is also reached from
    `.claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py`, which runs
    under a bare `python3` with no virtualenv, and that import walks through
    this file. `openai` and `httpx` are imported inside the functions that need
    them (`llm.py`, `dataforseo.py`), never at module scope.
  * **No import of `engine` or `agent`.** The API layer imports neither today.
    A forty-line OpenAI wrapper is cheaper than a new cross-layer dependency,
    and it keeps the writer runnable from a machine that has only `api/`.
"""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root() -> str:
    """The worktree root: the first ancestor that contains an `api/` directory.

    Walking up rather than hardcoding depth, because this file is reached both
    as `app.blog.content` from `api/` and through the skill shim, and because
    the repo is checked out into worktrees at varying paths.
    """
    d = _HERE
    while True:
        if os.path.isdir(os.path.join(d, "api")) and os.path.isdir(os.path.join(d, "docs")):
            return d
        parent = os.path.dirname(d)
        if parent == d:  # hit the filesystem root
            # Fall back to four levels up (api/app/blog/content -> repo root),
            # which is right for a normal checkout even if `docs/` is missing.
            return os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
        d = parent


def topic_bank_dir() -> str:
    return os.path.join(repo_root(), "docs", "seo", "topic-bank")


def axes_dir() -> str:
    return os.path.join(topic_bank_dir(), "axes")


def skills_dir() -> str:
    return os.path.join(repo_root(), ".claude", "skills")


def load_env() -> None:
    """Load the repo `.env` without clobbering anything already exported.

    `override=False` matters: CI and the test suite set their own values and a
    stale `.env` must not win over them.
    """
    path = os.path.join(repo_root(), ".env")
    if not os.path.isfile(path):
        return
    try:
        from dotenv import load_dotenv  # noqa: PLC0415 — optional at import time
    except ImportError:
        return
    load_dotenv(path, override=False)
