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


def workspace_dir(project_id: uuid.UUID) -> Path:
    """The project's workspace dir, shared by chat, headless, uploads, imports."""
    root = os.getenv("JOB_WORKDIR_ROOT") or tempfile.gettempdir()
    return Path(root) / "agent_projects" / str(project_id)
