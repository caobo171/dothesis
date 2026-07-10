"""F5 Task 2: DbProjectStateStore.commit_slice emits agent-quality events.

Monkeypatches app.analytics.emit so nothing leaves the process, then asserts the
store fires the raw state-transition signal:
- module_status_changed on a real status change,
- done_rejected_empty when the empty-done gate trips (before re-raising),
- needs_review_propagated when downstream modules are flagged.

Uses the shared DB fixtures (project_id/tmp_path) because the store reads/writes
status through the DB — the emit assertions are on the store's real behaviour,
not a stubbed one (F0: DB fixtures are fine here; only the emit sink is stubbed).
"""
import app.analytics as analytics
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def _store(project_id, tmp_path):
    return DbProjectStateStore(get_engine(), project_id, tmp_path)


def test_commit_emits_status_change(monkeypatch, project_id, tmp_path):
    events = []
    monkeypatch.setattr(analytics, "emit",
                        lambda e, uid, props=None: events.append((e, props)))
    _store(project_id, tmp_path).commit_slice("M1", {"research_title": "T"}, reason="x")
    assert any(e == "module_status_changed" for e, _ in events)


def test_empty_done_emits_rejected(monkeypatch, project_id, tmp_path):
    events = []
    monkeypatch.setattr(analytics, "emit",
                        lambda e, uid, props=None: events.append(e))
    store = _store(project_id, tmp_path)
    try:
        store.commit_slice("M5", {}, reason="x", confirm_done=True)  # empty-done -> ValueError
    except ValueError:
        pass
    assert "done_rejected_empty" in events


def test_downstream_flag_emits_needs_review(monkeypatch, project_id, tmp_path):
    events = []
    monkeypatch.setattr(analytics, "emit",
                        lambda e, uid, props=None: events.append((e, props)))
    store = _store(project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "g"}]}, reason="r", confirm_done=True)
    events.clear()
    # Mutating M1 again flags the started M2 downstream -> needs_review_propagated.
    store.commit_slice("M1", {"research_title": "T2"}, reason="pivot")
    assert any(e == "needs_review_propagated" for e, _ in events)
