"""Auto-decision audit trail (spec §4). Decisions ride INSIDE the owned slice,
written through commit_slice — a new top-level context_store key would
round-trip against this file store and VANISH in prod, because
DbProjectStateStore only persists SLICE_OWNERSHIP keys (the known CRITICAL
failure mode). The DB half of this proof lives in
api/tests/test_headless_db_roundtrip.py."""
import pytest

from agent.headless import record_decision
from agent.state import MODULES, SLICE_OWNERSHIP, ProjectStateStore


def _store(tmp_path):
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, "seed")
    return store


def test_decisions_key_is_owned_by_every_module():
    for m in MODULES:
        assert "decisions" in SLICE_OWNERSHIP[m]


def test_record_appends_to_owned_slice(tmp_path):
    store = _store(tmp_path)
    rec = record_decision(store, options=["Có", "Không"], choice="Có",
                          rationale="auto: first option")
    st = store.load()
    assert st["contextStore"]["decisions"] == [rec]
    assert rec["module"] == "M1" and rec["choice"] == "Có" and rec["ts"]

    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    assert len(store.load()["contextStore"]["decisions"]) == 2


def test_recorded_decision_does_not_satisfy_the_empty_done_gate(tmp_path):
    # `decisions` is owned by every module, so a naive _has_done_content would
    # count an audit append as the module's earned output and let a module with
    # NOTHING behind it be confirmed done — silently disabling the strict
    # done-gate (the hallucinated-completion catch). It bites hardest headless,
    # where the runner records a decision under every module it touches.
    store = _store(tmp_path)
    store.commit_slice("M5", {}, "focus M5", status_overrides={"M5": "in_progress"})
    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    with pytest.raises(ValueError, match="cannot mark M5 done"):
        store.commit_slice("M5", {}, "claim done", confirm_done=True)
    assert store.load()["status"]["M5"] == "in_progress"


def test_record_never_moves_the_state_machine(tmp_path):
    # commit_slice's normal side effects (module -> in_progress, downstream
    # needs_review) belong to CONTENT commits. An audit append must be inert:
    # a done module stays done, nothing gets flagged, focus stays put.
    store = _store(tmp_path)
    store.commit_slice("M1", {"research_questions": ["RQ1"]}, "finish M1",
                       confirm_done=True)
    store.commit_slice("M2", {"literature_sources": [{"title": "P"}]}, "start M2")
    before = store.load()
    record_decision(store, options=["Next", "Stop"], choice="Next", rationale="auto")
    after = store.load()
    assert after["status"] == before["status"]      # M1 still done, M2 in_progress
    assert after["focus"] == before["focus"]
