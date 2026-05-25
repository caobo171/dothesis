from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.supervisor import (
    RouteDecision, route_from_supervisor, supervisor_node,
)
from orchestrator.state import ContextStore


def _state(messages, cs=None, mode="interactive"):
    return {
        "messages": messages, "current_module": "M1",
        "context_store": cs or ContextStore(), "mode": mode,
        "user_intent": None, "pending_confirmations": [],
    }


def test_supervisor_routes_to_first_unconfirmed_in_auto():
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state([HumanMessage(content="...")], cs=cs, mode="auto")
    out = supervisor_node(state)
    assert out["current_module"] == "M3"


def test_supervisor_all_done_routes_to_done():
    cs = ContextStore(**{m: {"confirmed_at": "2026-05-26"} for m in
                         ("m1_topic", "m2_literature", "m3_design",
                          "m4_analysis", "m5_writing")})
    state = _state([HumanMessage(content="...")], cs=cs)
    out = supervisor_node(state)
    assert out["current_module"] == "DONE"


def test_supervisor_honors_navigation_request(monkeypatch):
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state(
        [HumanMessage(content="actually go back to M2 and redo it")],
        cs=cs,
    )
    # Stub the structured-output LLM to return a navigation intent.
    fake = MagicMock()
    fake.with_structured_output.return_value.invoke.return_value = type(
        "X", (), {"wants_navigation": True, "target_module": "M2", "confidence": 0.9}
    )()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", lambda: fake)
    out = supervisor_node(state)
    assert out["current_module"] == "M2"


def test_supervisor_auto_mode_skips_llm_classifier(monkeypatch):
    """Auto mode should never call the LLM classifier — only rules."""
    counter = {"calls": 0}
    def fake_llm():
        counter["calls"] += 1
        return MagicMock()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", fake_llm)

    cs = ContextStore()
    state = _state([HumanMessage(content="go back to M3")], cs=cs, mode="auto")
    supervisor_node(state)
    assert counter["calls"] == 0


def test_route_from_supervisor_returns_state_module():
    cs = ContextStore()
    state = {**_state([], cs=cs), "current_module": "M2"}
    assert route_from_supervisor(state) == "M2"
