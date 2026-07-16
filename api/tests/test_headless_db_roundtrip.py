"""NON-NEGOTIABLE Db round-trip for headless auto-decisions (spec §4).

DbProjectStateStore.load()/_save() iterate SLICE_OWNERSHIP and nothing else —
this is the test class that catches "works on the file store, dead in prod"."""
import asyncio
import json

from agent.headless import RunProfile, record_decision, run_headless
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


def test_stall_detection_against_db_load_shape(project_id, tmp_path):
    # run_headless detects stalls by diffing store.load() across a turn, so the
    # SHAPE of load() decides what counts as progress — and the two stores
    # disagree. ProjectStateStore.load() carries a versionHistory that grows a
    # timestamped entry per commit; DbProjectStateStore.load() hardcodes
    # versionHistory=[] (agent_state.py), leaving status+focus+contextStore.
    # Prod is therefore STRICTER: a repeated identical commit reads as progress
    # under the file store and as a stall here. agent/tests can't import app.*,
    # so this is the only place the prod comparison shape gets a guard.
    stall = {"scenario": "db-stall", "entry": "continue", "steps": [
        {"response": "Hmm, let me think."},
        {"response": "Still thinking."},
        {"response": "Thinking harder."},
    ]}
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "run.json").write_text(json.dumps(stall), encoding="utf-8")

    from langgraph.checkpoint.memory import InMemorySaver

    from agent.runtime import build_agent
    from agent.testing.fake_model import FakeChatModel

    store = DbProjectStateStore(get_engine(), project_id, tmp_path)
    agent = build_agent(tmp_path / "proj",
                        model=FakeChatModel.from_fixtures_dir(str(fx)),
                        checkpointer=InMemorySaver(), store=store)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_stalls=3, max_turns=10)))
    assert result.status == "failed" and result.reason == "max_stalls"
    assert result.turns == 3
