"""Brief §1.8 — token meter at the LLM call boundary.

The meter wraps bounded_invoke with estimate → reserve → reconcile. Tests
pin: (1) the response passes through unchanged, (2) the ledger records
real usage when the LLM returns usage_metadata, (3) the ledger STILL
records on failure (zero tokens but real duration), (4) sink errors do
NOT escape and break the request.
"""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from orchestrator import token_meter


def _fake_llm(content: str = "ok", *, input_tokens=12, output_tokens=8):
    """Build a LangChain-shaped chat model with usage_metadata."""
    llm = MagicMock()
    resp = MagicMock()
    resp.content = content
    resp.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    llm.invoke.return_value = resp
    llm.model = "gemini-2.5-flash"
    return llm


@pytest.fixture
def captured_entries():
    """Replace the persistence sink with an in-memory list. Restored on
    teardown so cross-test sink state can't leak."""
    entries: list[token_meter.LedgerEntry] = []
    prev = token_meter._SINK
    token_meter.register_sink(entries.append)
    yield entries
    token_meter._SINK = prev


def test_metered_invoke_returns_llm_response(captured_entries):
    llm = _fake_llm("hi")
    resp = token_meter.metered_invoke(
        llm, "test prompt", action_kind="unit_test", max_seconds=5,
    )
    assert resp.content == "hi"


def test_metered_invoke_records_real_token_usage(captured_entries):
    pid = uuid4()
    llm = _fake_llm(input_tokens=120, output_tokens=42)
    token_meter.metered_invoke(
        llm, "test prompt", action_kind="router_pick",
        project_id=pid, max_seconds=5,
    )
    assert len(captured_entries) == 1
    e = captured_entries[0]
    assert e.project_id == pid
    assert e.action_kind == "router_pick"
    assert e.prompt_tokens == 120
    assert e.completion_tokens == 42
    assert e.model == "gemini-2.5-flash"
    # Reserved should be > 0 (chars/4 of "test prompt") — exact value isn't
    # the contract, just "non-zero so the reservation has meaning".
    assert e.reserved > 0
    assert e.duration_ms >= 0


def test_metered_invoke_records_on_llm_failure(captured_entries):
    # Cost forensics: a failed call still went out (still cost network
    # quota, still consumed an attempt against rate limits). The ledger
    # must record it — zero tokens but real duration.
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("Gemini transport error")
    llm.model = "gemini-2.5-flash"
    with pytest.raises(RuntimeError):
        token_meter.metered_invoke(
            llm, "p", action_kind="failed_call", max_seconds=2, retries=0,
        )
    assert len(captured_entries) == 1
    e = captured_entries[0]
    assert e.prompt_tokens == 0
    assert e.completion_tokens == 0
    assert e.duration_ms >= 0


def test_sink_failure_does_not_break_call():
    # The sink runs in the response-handling path of every LLM call. A
    # failing sink (e.g. DB down) must NOT propagate as a user-facing
    # error — we'd lose every chat turn the moment the ledger DB hiccups.
    def _bad_sink(_entry):
        raise RuntimeError("DB down")
    prev = token_meter._SINK
    token_meter.register_sink(_bad_sink)
    try:
        llm = _fake_llm("still works")
        resp = token_meter.metered_invoke(
            llm, "p", action_kind="t", max_seconds=5,
        )
        assert resp.content == "still works"
    finally:
        token_meter._SINK = prev


def test_estimate_tokens_handles_message_lists():
    # Real prompts are lists of langchain Message objects, not strings.
    msg1 = MagicMock(); msg1.content = "abcd" * 100      # 400 chars
    msg2 = MagicMock(); msg2.content = "xyz" * 50        # 150 chars
    estimate = token_meter.estimate_tokens([msg1, msg2])
    # 550 chars / 4 = 137. Loose bound — just verify it's in the ballpark.
    assert 100 < estimate < 200


def test_no_project_id_still_runs_through(captured_entries):
    # Eval/intake paths use the meter without a project_id. Still records
    # for the model-level cost aggregate, just nullable on project.
    llm = _fake_llm()
    token_meter.metered_invoke(
        llm, "p", action_kind="eval_run", project_id=None, max_seconds=5,
    )
    assert len(captured_entries) == 1
    assert captured_entries[0].project_id is None
