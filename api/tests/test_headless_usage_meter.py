"""Headless runs must emit token_usage events or auto-draft is free.

_charge_auto_run sums token_ledger per model, and those rows are written
API-side by job_runner._ingest_event from `token_usage` events on the
events.jsonl contract (job_runner.py:215-236). The deep agent never goes
through orchestrator.token_meter, so the runner has to emit its own.

No DB here on purpose: the subprocess is not the DB writer, so the unit under
test is the event it emits.
"""
import uuid

from app.headless_entry import _UsageMeter


class _Appender:
    def __init__(self):
        self.events = []

    def write(self, ev):
        self.events.append(ev)


def test_usage_events_are_summed_per_model_and_emitted_once_per_flush():
    pid = uuid.uuid4()
    appender = _Appender()
    meter = _UsageMeter(pid, appender)
    meter.observe({"type": "usage", "input_tokens": 1000,
                   "output_tokens": 500, "model": "gemini-2.5-flash"})
    meter.observe({"type": "usage", "input_tokens": 200,
                   "output_tokens": 100, "model": "gemini-2.5-flash"})
    assert meter.flush() == 1

    (ev,) = appender.events
    assert ev["type"] == "token_usage"
    assert ev["action_kind"] == "deep_agent_turn"
    assert ev["model"] == "gemini-2.5-flash"
    assert ev["prompt_tokens"] == 1200
    assert ev["completion_tokens"] == 600
    assert ev["project_id"] == str(pid)
    # NOT NULL columns on token_ledger; _ingest_event coerces via int().
    assert ev["reserved"] == 0 and "duration_ms" in ev


def test_each_model_gets_its_own_event():
    """_charge_auto_run prices each row at its own model's rate, so a turn that
    failed over to a second model must not be collapsed into one."""
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5,
                   "model": "gemini-2.5-flash"})
    meter.observe({"type": "usage", "input_tokens": 20, "output_tokens": 7,
                   "model": "gpt-5.6-luna"})
    assert meter.flush() == 2
    assert {e["model"] for e in appender.events} == {"gemini-2.5-flash",
                                                     "gpt-5.6-luna"}


def test_flush_is_empty_when_no_usage_was_seen():
    appender = _Appender()
    assert _UsageMeter(uuid.uuid4(), appender).flush() == 0
    assert appender.events == []


def test_flush_clears_the_buffer_so_turns_are_not_double_billed():
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5,
                   "model": "m"})
    meter.flush()
    assert meter.flush() == 0
    assert len(appender.events) == 1


def test_non_usage_events_are_ignored():
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "tool_start", "name": "commit_slice"})
    meter.observe({"type": "done"})
    assert meter.flush() == 0
