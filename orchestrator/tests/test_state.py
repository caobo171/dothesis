from datetime import datetime
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.state import (
    ContextStore, OrchestratorState, get_module_slice, next_unconfirmed_module,
)


def test_context_store_default_empty():
    cs = ContextStore()
    for m in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(cs, m) is None


def test_context_store_roundtrip_jsonb():
    cs = ContextStore(m1_topic={"research_title": "X"})
    blob = cs.model_dump()
    assert blob["m1_topic"] == {"research_title": "X"}
    cs2 = ContextStore.model_validate(blob)
    assert cs2.m1_topic == {"research_title": "X"}


def test_next_unconfirmed_walks_in_order():
    cs = ContextStore()
    assert next_unconfirmed_module(cs) == "M1"
    cs.m1_topic = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M2"
    cs.m2_literature = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m3_design = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m4_analysis = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M5"
    cs.m5_writing = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "DONE"


def test_get_module_slice_returns_only_relevant_field():
    cs = ContextStore(m1_topic={"a": 1}, m2_literature={"b": 2})
    assert get_module_slice(cs, "M1") == {"a": 1}
    assert get_module_slice(cs, "M2") == {"b": 2}
    assert get_module_slice(cs, "M3") == {}


def test_orchestrator_state_construction():
    state: OrchestratorState = {
        "project_id": uuid4(),
        "thread_id": uuid4(),
        "messages": [HumanMessage(content="hi")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    assert state["current_module"] == "M1"
    assert state["mode"] == "interactive"
