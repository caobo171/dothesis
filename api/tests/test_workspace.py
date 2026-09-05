"""The project workspace path helper — one definition, no surface attached."""
import subprocess
import sys
import tempfile
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


def test_a_relative_root_resolves_to_the_same_place_from_any_cwd(monkeypatch):
    """The bug this exists for, measured on a real project:

        api/var/jobs/agent_projects/<pid>/uploads/Results.docx   ← the API wrote it
        var/jobs/agent_projects/<pid>/                           ← the run looked here, empty

    `JOB_WORKDIR_ROOT=./var/jobs` is relative, and job_runner spawns the run
    with cwd=<repo root> (job_runner.py:70,482) while the API serves from
    api/. Same env var, same project, two directories — so M4 could not find
    the dataset the student had uploaded, refused to invent numbers, and
    flagged the same blocker seven times.
    """
    monkeypatch.setenv("JOB_WORKDIR_ROOT", "./var/jobs")
    pid = uuid4()

    monkeypatch.chdir(Path(__file__).resolve().parents[1])          # api/
    from_api = workspace_dir(pid)
    monkeypatch.chdir(Path(__file__).resolve().parents[2])          # repo root
    from_repo_root = workspace_dir(pid)

    assert from_api == from_repo_root
    assert from_api.is_absolute()


def test_an_absolute_root_is_left_alone(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    pid = uuid4()
    assert workspace_dir(pid) == tmp_path / "agent_projects" / str(pid)


def test_an_unset_root_still_falls_back_to_the_temp_dir(monkeypatch):
    monkeypatch.delenv("JOB_WORKDIR_ROOT", raising=False)
    pid = uuid4()
    assert workspace_dir(pid) == (
        Path(tempfile.gettempdir()) / "agent_projects" / str(pid))


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
