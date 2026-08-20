"""Headless runs must emit token_usage events or auto-draft is free.

_charge_auto_thesis_run sums token_ledger per model, and those rows are written
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
    """_charge_auto_thesis_run prices each row at its own model's rate, so a turn that
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


def _openai_route(monkeypatch):
    """Pin the CONFIGURED model so the fallback is a known id: route=openai with
    no override resolves to gpt-5.6-luna (agent/model_factory.spec_from_env)."""
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "openai")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_an_unpriced_served_model_never_becomes_the_ledger_label(monkeypatch):
    """C1: _charge_auto_thesis_run prices every ledger row through credit_multiplier,
    which bills anything missing from quality/model_prices.py at the 4.0x
    UNKNOWN_MODEL_MULTIPLIER. A dated snapshot id is exactly that — and on the
    openai route (luna = 0.53x) it would overbill a whole thesis 7.6x. The label
    must fall back to the configured model instead."""
    _openai_route(monkeypatch)
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 900, "output_tokens": 100,
                   "model": "gpt-5.6-luna-2026-05-13"})  # a real-shaped snapshot id
    assert meter.flush() == 1

    (ev,) = appender.events
    from app.pricing import is_priced
    assert is_priced(ev["model"]), \
        f"{ev['model']!r} would bill at the unknown-model fallback"
    assert ev["model"] == "gpt-5.6-luna"
    # Tokens are not lost in the relabel — only the label changes.
    assert ev["prompt_tokens"] == 900 and ev["completion_tokens"] == 100


def test_a_missing_served_model_falls_back_to_the_configured_one(monkeypatch):
    """runtime.py only sets `model` when response_metadata carries it, which most
    routes do not. "unknown" is unpriced, so it billed at 4.0x too."""
    _openai_route(monkeypatch)
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5})
    meter.flush()

    from app.pricing import is_priced
    assert appender.events[0]["model"] == "gpt-5.6-luna"
    assert is_priced(appender.events[0]["model"])


def test_a_priced_served_model_is_still_kept(monkeypatch):
    """The fallback must not flatten a REAL failover: a served id the table
    prices still bills at its own rate (that is why the split exists)."""
    _openai_route(monkeypatch)
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5,
                   "model": "claude-sonnet-4-6"})
    meter.flush()
    assert appender.events[0]["model"] == "claude-sonnet-4-6"


def test_non_usage_events_are_ignored():
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "tool_start", "name": "commit_slice"})
    meter.observe({"type": "done"})
    assert meter.flush() == 0
