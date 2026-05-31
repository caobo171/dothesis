from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.supervisor import (
    IntentClassification, RouteDecision, route_from_supervisor, supervisor_node,
)
from orchestrator.state import ContextStore


def test_supervisor_skips_nav_while_module_mid_question(monkeypatch):
    """When the current module is awaiting an answer, the user's reply is an
    ANSWER, not navigation — the nav classifier must be skipped so domain answers
    like 'PLS-SEM' don't wrongly jump to M4."""
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    cs = ContextStore(m1_topic={"confirmed_at": "x"}, m2_literature={"confirmed_at": "x"},
                      m3_design={"_awaiting_field": "design"})
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = IntentClassification(
        wants_navigation=True, target_module="M4", confidence=0.95)
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    out = supervisor_node({
        "messages": [HumanMessage(content="PLS-SEM")], "current_module": "M3",
        "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert out["current_module"] == "M3"           # stayed (nav skipped)
    fake_structured.invoke.assert_not_called()     # classifier not even consulted


def _state(messages, cs=None, mode="interactive"):
    return {
        "messages": messages, "current_module": "M1",
        "context_store": cs or ContextStore(), "mode": mode,
        "user_intent": None, "pending_confirmations": [],
    }


def test_supervisor_target_routes_to_ready_chapter_skipping_modules():
    # topic + literature confirmed. Target = ch_lit_review (needs only literature,
    # which is done) → ready → route M5. The sequential rule would go to M3.
    cs = ContextStore(m1_topic={"confirmed_at": "x"},
                      m2_literature={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "ch_lit_review"
    out = supervisor_node(state)
    assert out["current_module"] == "M5"


def test_supervisor_target_methodology_skips_analysis():
    # topic + literature + design confirmed. Target = ch_methodology (needs only
    # design) → ready → M5. Sequential would route to M4 (analysis).
    cs = ContextStore(m1_topic={"confirmed_at": "x"},
                      m2_literature={"confirmed_at": "x"},
                      m3_design={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "ch_methodology"
    out = supervisor_node(state)
    assert out["current_module"] == "M5"


def test_supervisor_target_backfills_blocked_prerequisite():
    # Target = analysis, nothing done → backfill topic first → M1.
    state = _state([], cs=ContextStore())
    state["target_artifact"] = "analysis"
    out = supervisor_node(state)
    assert out["current_module"] == "M1"


def test_supervisor_clears_target_once_reached():
    # Target = analysis, already confirmed → reached → clear + resume sequential.
    cs = ContextStore(m4_analysis={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "analysis"
    out = supervisor_node(state)
    assert "target_artifact" in out and out["target_artifact"] is None
    assert out["current_module"] == "M1"


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
