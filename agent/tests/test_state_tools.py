"""Tool bindings over the guarded store (F2 Task 4). The tools close over a
real file-backed ProjectStateStore so we exercise the actual upsert/resolve path,
not a mock — the blocker must persist and flip status without touching modules."""
import json
import uuid

from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


def test_flag_and_resolve_blocker(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    assert "flag_blocker" in tools and "resolve_blocker" in tools

    out = json.loads(tools["flag_blocker"].func(
        module="M4", substep="interpret", title="HTMT fails", why="validity"))
    assert out["status"] == "open" and out["module"] == "M4"

    res = json.loads(tools["resolve_blocker"].func(task_id=out["id"]))
    assert res["resolved"] is True
    assert store.load()["contextStore"]["roadmap_tasks"][0]["status"] == "done"
