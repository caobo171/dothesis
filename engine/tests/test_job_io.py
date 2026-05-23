import json
from pathlib import Path

from engine.job_io import JobStreamer, JobTracker, JsonlAppender


def test_appender_writes_one_line_per_call(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    a = JsonlAppender(p)
    a.write({"type": "activity", "text": "hello"})
    a.write({"type": "activity", "text": "world"})
    a.close()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["text"] for l in lines] == ["hello", "world"]


def test_tracker_emits_activity_and_progress(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    a = JsonlAppender(p)
    tr = JobTracker(a)
    tr.log_activity("did a thing", phase="research", agent="Scout")
    tr.update_phase("compose", progress_percent=68, details={"active_agents": ["Crafter · Intro"]})
    a.close()
    events = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert events[0]["type"] == "activity"
    assert events[0]["phase"] == "research"
    assert events[0]["agent"] == "Scout"
    assert events[0]["text"] == "did a thing"
    assert events[1]["type"] == "phase_progress"
    assert events[1]["phase"] == "compose"
    assert abs(events[1]["progress"] - 0.68) < 1e-6
    assert events[1]["active_agents"] == ["Crafter · Intro"]


def test_tracker_has_full_engine_surface(tmp_path: Path):
    """Engine's draft_generator.py and phase modules call these — they must all exist."""
    a = JsonlAppender(tmp_path / "e.jsonl")
    tr = JobTracker(a)
    # cancellation / heartbeat are no-ops
    tr.check_cancellation()
    tr.send_heartbeat()
    # other surfaces shouldn't raise
    tr.log_source_found("My Paper", authors=["A. Doe"], year=2024, doi="10.1/x", url="http://x", verified=True)
    tr.update_research(sources_count=12, phase_detail="halfway through cascade")
    tr.update_exporting(export_type="pdf")
    tr.mark_completed()
    tr.mark_failed("oops")
    assert tr.to_json() == {}
    tr.print_report()
    a.close()
    # Each non-no-op call wrote one event; cancellation/heartbeat/to_json/print_report did not.
    lines = (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5


def test_streamer_emits_activity(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    a = JsonlAppender(p)
    s = JobStreamer(a)
    s("hello", phase="research")
    a.close()
    ev = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert ev == {"type": "activity", "text": "hello", "phase": "research"}
