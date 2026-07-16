"""The project workspace path helper — one definition, no surface attached."""
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from app.workspace import workspace_dir


def test_chat_v3_reexport_is_the_same_helper():
    # Many callers still do `from .chat_v3 import _workspace_dir`; they must
    # resolve to the identical path, not a second implementation.
    from app.routers.chat_v3 import _workspace_dir
    pid = uuid4()
    assert _workspace_dir is workspace_dir
    assert workspace_dir(pid).name == str(pid)


def test_workspace_root_follows_job_workdir_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    pid = uuid4()
    assert workspace_dir(pid) == tmp_path / "agent_projects" / str(pid)


def test_workspace_helper_pulls_in_no_router():
    # The path helper every surface needs must not drag a surface behind it:
    # it used to live in the chat router, so the headless subprocess imported
    # the whole FastAPI chat surface to resolve a directory — the exact
    # chat-gates-headless coupling RunProfile's docstring forbids. Fresh
    # interpreter, because in-process the routers are already imported by other
    # tests' app fixtures and sys.modules would prove nothing.
    code = ("import sys; import app.workspace; "
            "sys.exit(1 if any(m.startswith('app.routers') for m in sys.modules) "
            "else 0)")
    assert subprocess.run([sys.executable, "-c", code],
                          cwd=Path(__file__).resolve().parents[1]).returncode == 0
