"""DB round-trip for coaching keys — the F0/A2 regression test.

Planned features (roadmap coaching, advisor-feedback tracking, institution
profile, thesis timeline) write into context_store keys OUTSIDE the M1-M5
slice map. DbProjectStateStore.load()/_save() used to only know about the
module columns, so any other key was silently dropped on the next load()
(see project_db_store_persistence_gap memory). This proves the `coaching`
JSONB column (added in Task A1) actually round-trips them.
"""
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def test_coaching_keys_round_trip_in_db(project_id):
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    st = store.load()
    st["contextStore"]["roadmap_tasks"] = [{"id": "b1", "status": "open", "title": "x"}]
    st["contextStore"]["institution_profile"] = {"citation_style": "apa7"}
    store._save(st)
    reloaded = store.load()  # fresh read from DB, not the in-memory dict
    assert reloaded["contextStore"]["roadmap_tasks"][0]["id"] == "b1"
    assert reloaded["contextStore"]["institution_profile"]["citation_style"] == "apa7"
    # module ownership still works and is unaffected by the coaching lift
    assert "m1_topic" not in reloaded["contextStore"]


def test_exists_ignores_coaching_only_state(project_id):
    # A fresh project that only has coaching data (e.g. F4 seeded an
    # institution_default) must still report exists=False — otherwise
    # onboarding treats every new project as "already started".
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    st = store.load()
    st["contextStore"]["institution_profile"] = {"citation_style": "apa7"}
    store._save(st)
    assert store.exists() is False


def test_read_api_returns_persisted_coaching(project_id):
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    st = store.load(); st["contextStore"]["advisor_feedback"] = [{"id": "1", "status": "open"}]
    store._save(st)
    assert store.get_advisor_feedback()[0]["id"] == "1"
    assert store.get_institution_profile() == {}


def test_upsert_roadmap_task_round_trips_in_db(project_id):
    # F2 Task 3's dedicated coaching write path must persist through the DB store
    # (not only the file store), since roadmap_tasks lives in the coaching column.
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    t = store.upsert_roadmap_task({"module": "M4", "title": "HTMT fails",
                                   "why": "validity", "status": "open"})
    reloaded = DbProjectStateStore(get_engine(), project_id, "/tmp/ws").load()
    tasks = reloaded["contextStore"]["roadmap_tasks"]
    assert tasks[0]["id"] == t["id"] and tasks[0]["title"] == "HTMT fails"
