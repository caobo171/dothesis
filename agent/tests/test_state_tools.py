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


def test_ingest_creates_feedback_and_blockers(tmp_path, monkeypatch):
    import agent.feedback as fb
    monkeypatch.setattr(fb, "extract_directives", lambda t: [
        {"chapter": "results", "issue": "add effect sizes", "required_change": "Cohen f2"}])
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["ingest_advisor_feedback"].func(feedback_text="please add effect sizes"))
    assert out["added"] == 1
    cs = store.load()["contextStore"]
    assert cs["advisor_feedback"][0]["issue"] == "add effect sizes"
    assert len(cs["roadmap_tasks"]) == 1              # a blocker was created


def test_mark_feedback_addressed_clears_blocker(tmp_path, monkeypatch):
    import agent.feedback as fb
    monkeypatch.setattr(fb, "extract_directives", lambda t: [
        {"chapter": "results", "issue": "add effect sizes", "required_change": "Cohen f2"}])
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    tools["ingest_advisor_feedback"].func(feedback_text="x")
    fid = store.load()["contextStore"]["advisor_feedback"][0]["id"]
    out = json.loads(tools["mark_feedback_addressed"].func(feedback_id=fid))
    assert out["addressed"] is True
    cs = store.load()["contextStore"]
    assert cs["advisor_feedback"][0]["status"] == "addressed"
    assert cs["roadmap_tasks"][0]["status"] == "done"   # linked blocker cleared
