"""Where a project's agent workspace lives on disk — one definition, no router.

Deliberately neutral (no FastAPI, no models, no router imports): every surface
needs this path, and it used to live in `routers.chat_v3`. That made the headless
subprocess import the whole chat router — and the interactive chat surface — just
to resolve a directory, which is exactly the chat-gates-headless coupling
RunProfile's docstring says must be impossible. A path helper cannot be allowed
to drag a surface behind it.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


# Anchor for a relative JOB_WORKDIR_ROOT. api/app/workspace.py -> the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def workspace_dir(project_id: uuid.UUID) -> Path:
    """The project's workspace dir, shared by chat, headless, uploads, imports.

    Always absolute, and a relative JOB_WORKDIR_ROOT is anchored at the repo
    root rather than at whatever the calling process's cwd happens to be.

    That difference is not cosmetic. The API serves from `api/`, job_runner
    spawns the run with `cwd=<repo root>` (job_runner.py:70,482) and the
    interactive-headless spawn uses `cwd=api/` (job_runner.py:412). With
    `JOB_WORKDIR_ROOT=./var/jobs` those are three different workspaces for one
    project, and it showed: routers/uploads.py mirrored a student's dataset into
    `api/var/jobs/agent_projects/<pid>/uploads/`, the run created an empty
    `var/jobs/agent_projects/<pid>/` and found nothing there, so M4 reported it
    had no data, refused to invent numbers, and flagged the same blocker seven
    times over a file that was sitting on disk the whole run.
    """
    root = os.getenv("JOB_WORKDIR_ROOT") or tempfile.gettempdir()
    path = Path(root)
    # Only the relative case is touched. An absolute root is passed through
    # exactly as given: resolving it too would rewrite /var/... to /private/var/
    # on macOS and move every workspace that already exists under the old
    # spelling, which is a bigger change than the bug being fixed.
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    return path / "agent_projects" / str(project_id)
