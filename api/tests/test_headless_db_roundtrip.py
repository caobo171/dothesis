"""NON-NEGOTIABLE Db round-trip for headless auto-decisions (spec §4).

DbProjectStateStore.load()/_save() iterate SLICE_OWNERSHIP and nothing else —
this is the test class that catches "works on the file store, dead in prod"."""
from agent.headless import record_decision
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def test_decisions_round_trip_through_db(project_id, tmp_path):
    store = DbProjectStateStore(get_engine(), project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, "seed")
    rec = record_decision(store, options=["Có", "Không"], choice="Có",
                          rationale="auto: first option")
    # Fresh store = fresh DB read, no in-memory carryover.
    reloaded = DbProjectStateStore(get_engine(), project_id, tmp_path).load()
    assert reloaded["contextStore"]["decisions"][0]["choice"] == "Có"
    assert reloaded["contextStore"]["decisions"][0]["module"] == rec["module"]


def test_decision_recording_keeps_status_in_db(project_id, tmp_path):
    store = DbProjectStateStore(get_engine(), project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T", "research_questions": ["RQ"]},
                       "seed", confirm_done=True)
    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    reloaded = DbProjectStateStore(get_engine(), project_id, tmp_path).load()
    assert reloaded["status"]["M1"] == "done"   # audit append didn't regress it
