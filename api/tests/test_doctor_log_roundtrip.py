"""DB round-trip for the recovery doctor's repair ledger.

`_save()` writes only the columns it knows about, so a context_store column
left out of an explicit load/save pair is silently dropped on the next commit.
That has already cost this codebase a dead key in production once — see
test_agent_state_coaching.py for the same regression on `coaching`. The
doctor's ledger is what stops a repair looping forever, so losing it is not a
cosmetic failure: it bills the student for the same repair every turn.
"""
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def test_doctor_log_round_trips(project_id):
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    assert store.load_doctor_log() == {}

    store.save_doctor_log({"RESULTS_NOT_IN_STATE": {
        "gaps_before": ["results is empty"], "gaps_after": [], "exhausted": False}})

    # Fresh instance — a real read from the database, not an in-memory dict.
    log = DbProjectStateStore(get_engine(), project_id, "/tmp/ws").load_doctor_log()
    assert log["RESULTS_NOT_IN_STATE"]["gaps_before"] == ["results is empty"]
    assert log["RESULTS_NOT_IN_STATE"]["exhausted"] is False


def test_saving_the_log_does_not_disturb_module_slices(project_id):
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    store.commit_slice("M1", {"research_title": "T"}, reason="test")

    store.save_doctor_log({"FALSE_DONE": {"exhausted": True}})

    fresh = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    assert fresh.load_full_context_store()["m1_topic"]["research_title"] == "T"
    assert fresh.load_doctor_log()["FALSE_DONE"]["exhausted"] is True


def test_committing_a_slice_does_not_wipe_the_log(project_id):
    """The ledger outlives ordinary state writes.

    `doctor` is deliberately outside SLICE_OWNERSHIP, so commit_slice has no
    business touching it. If it did, every repair would look brand new on the
    next turn and the loop guard would never fire.
    """
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    store.save_doctor_log({"FALSE_DONE": {"exhausted": True}})

    store.commit_slice("M1", {"research_title": "T"}, reason="test")

    assert DbProjectStateStore(get_engine(), project_id, "/tmp/ws") \
        .load_doctor_log() == {"FALSE_DONE": {"exhausted": True}}
