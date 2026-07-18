"""Workspace path confinement (boundary hardening, gap 1a).

The one place that turns a caller-supplied data-file path into a real path that
is PROVABLY inside the project workspace. Every `run_stats` op and every parser
resolves through here at entry, so a prompt-injected `/etc/passwd` or a `..`
traversal is refused before any file is opened.

The rule (borrowed from grok-build's sandbox deny logic, which realpath-resolves
both sides and treats an inexpressible/unresolvable path as denied, never
silently allowed — `crates/codegen/xai-grok-sandbox/src/deny/mod.rs:139-151`):
resolve the workspace root and the candidate to absolute real paths (following
symlinks), then require containment. Anything that can't be resolved, or that
lands outside, raises `WorkspaceEscapeError`.

This is a SECURITY boundary → fail-CLOSED (unlike the rest of the pipeline, which
fails open for legitimate-but-imperfect work). Pure, stdlib-only, no I/O beyond
`Path.resolve()` stat calls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union


class WorkspaceEscapeError(ValueError):
    """The requested path resolves outside the project workspace (or can't be
    resolved). A subclass of ValueError so existing `except ValueError` sites
    keep catching it."""


def resolve_data_path(file: Union[str, Path, None], root: Union[str, Path],
                      *, must_exist: bool = False) -> Path:
    """Resolve `file` against the workspace `root` and prove it stays inside.

    Returns the resolved absolute Path. Raises:
      - ValueError if `file` is empty/None (a caller bug, not an escape).
      - WorkspaceEscapeError if the path resolves outside root, or cannot be
        resolved at all (inexpressible ⇒ denied).
      - FileNotFoundError if must_exist and the resolved file does not exist
        (existence is otherwise the caller's concern — the resolver never
        requires it, so a not-yet-written derived file still resolves).
    """
    if file is None or (isinstance(file, str) and not file.strip()):
        raise ValueError("data file path is empty")
    try:
        root_r = Path(root).resolve(strict=False)
        cand = Path(file)
        # A relative path is anchored at the workspace root, never the process CWD.
        cand = cand if cand.is_absolute() else (root_r / cand)
        cand_r = cand.resolve(strict=False)
    except Exception as exc:   # OSError on symlink loops, etc. — inexpressible ⇒ deny
        raise WorkspaceEscapeError(f"path could not be resolved: {file!r} ({exc})") from exc
    if not (cand_r == root_r or cand_r.is_relative_to(root_r)):
        raise WorkspaceEscapeError(
            f"path resolves outside the project workspace: {file!r}")
    if must_exist and not cand_r.exists():
        raise FileNotFoundError(str(cand_r))
    return cand_r
