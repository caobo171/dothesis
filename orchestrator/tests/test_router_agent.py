"""Stage-1 router-agent tests.

Covers the two short-circuits (cold-start, awaiting-field), the LLM-pick
path with a scripted tool choice, the PLS-SEM regression (domain answer
must not be classified as nav), and the LLM-failure fallback. Integration
tests for the full graph_v2 round-trip live in tests/integration/."""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents import router_agent
from orchestrator.agents.base import ModuleStepResult
from orchestrator.state import ContextStore


def _state(messages, cs=None):
    return {
        "project_id": None, "thread_id": None,
        "messages": messages, "current_module": "M1",
        "context_store": cs or ContextStore(), "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    }


def _stub_agent(monkeypatch, module_key: str, transition: bool = False,
                msg: str = "ok"):
    """Replace the singleton ModuleAgent for `module_key` with a stub
    whose .step() returns a deterministic ModuleStepResult. Returns the
    stub so tests can assert on call args."""
    stub = MagicMock()
    stub.step.return_value = ModuleStepResult(
        assistant_message=msg,
        context_patch={},
        transition=transition,
        needs_user_reply=not transition,
    )
    monkeypatch.setitem(router_agent._AGENT_BY_KEY, module_key, stub)
    return stub


def test_cold_start_short_circuits_to_m1_without_llm(monkeypatch):
    """Cold-start (no module confirmed): router MUST pick M1 without
    invoking the LLM. The first turn of every project is M1 — there is
    nothing to route between, so paying for a Gemini call is pure waste
    (and was a measurable latency hit on the v1 supervisor before the
    cold-start fast-path was added there)."""
    m1 = _stub_agent(monkeypatch, "M1")
    # Sentinel: any LLM call would raise.
    monkeypatch.setattr(router_agent, "_router_llm",
                        lambda: (_ for _ in ()).throw(AssertionError("LLM called")))

    picked, result, _intent = router_agent.route_turn(_state([HumanMessage(content="Hello")]))
    assert picked == "M1"
    assert result.assistant_message == "ok"
    m1.step.assert_called_once()


def test_awaiting_field_short_circuits_to_that_module(monkeypatch):
    """When any module slice has `_awaiting_field` set, the user's reply
    is an ANSWER to a pending question. Routing elsewhere would lose the
    answer — and risk the PLS-SEM-as-nav class of false positive. Skip
    the LLM and call that module directly."""
    cs = ContextStore(
        m1_topic={"confirmed_at": "x"},
        m2_literature={"confirmed_at": "x"},
        m3_design={"_awaiting_field": "design"},
    )
    m3 = _stub_agent(monkeypatch, "M3")
    monkeypatch.setattr(router_agent, "_router_llm",
                        lambda: (_ for _ in ()).throw(AssertionError("LLM called")))

    picked, _, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="PLS-SEM")], cs=cs))
    assert picked == "M3"  # NOT M4 — the regression case
    m3.step.assert_called_once()


def test_llm_pick_dispatches_chosen_module(monkeypatch):
    """When neither short-circuit applies (≥1 module confirmed AND no
    awaiting field), the router asks the LLM which module-tool to call,
    parses the tool_calls list, and dispatches to the matching agent.
    Confirms the tool-name → module-key mapping is wired correctly."""
    cs = ContextStore(m1_topic={"confirmed_at": "x"})  # M1 done, M2-5 not, none awaiting
    m4 = _stub_agent(monkeypatch, "M4", msg="m4 reply")

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    # Gemini-shaped tool_calls: list of dicts with "name" key.
    fake_bound.invoke.return_value = AIMessage(
        content="", tool_calls=[{"name": "m4_analysis_step",
                                  "args": {"user_intent": "do analysis"},
                                  "id": "1"}])
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    picked, result, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="run the analysis")], cs=cs))
    assert picked == "M4"
    assert result.assistant_message == "m4 reply"
    m4.step.assert_called_once()


def test_llm_failure_falls_back_to_next_unconfirmed(monkeypatch):
    """Any LLM exception (timeout, transport, schema) must NOT hang the
    turn — fall back to the rule-based pick (next unconfirmed module).
    This is the same defense the v1 supervisor has and we must preserve
    it so v2 isn't more fragile."""
    cs = ContextStore(m1_topic={"confirmed_at": "x"})  # next unconfirmed = M2
    m2 = _stub_agent(monkeypatch, "M2", msg="m2 reply")

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    fake_bound.invoke.side_effect = RuntimeError("simulated transport error")
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    picked, result, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="anything")], cs=cs))
    assert picked == "M2"
    assert result.assistant_message == "m2 reply"
    m2.step.assert_called_once()


def test_llm_returns_no_tool_calls_falls_back(monkeypatch):
    """Defense for Gemini's safety-filter case: content="" with no
    tool_calls. tool_choice="any" SHOULD make this impossible but we've
    been bitten by Gemini returning empty before — never assume."""
    cs = ContextStore(m1_topic={"confirmed_at": "x"})
    m2 = _stub_agent(monkeypatch, "M2")

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    fake_bound.invoke.return_value = AIMessage(content="", tool_calls=[])
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    picked, _, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="anything")], cs=cs))
    assert picked == "M2"


def test_llm_picks_unknown_tool_falls_back(monkeypatch):
    """If the LLM hallucinates a tool name that isn't in our toolbox,
    don't crash — fall back to rules."""
    cs = ContextStore(m1_topic={"confirmed_at": "x"})
    m2 = _stub_agent(monkeypatch, "M2")

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    fake_bound.invoke.return_value = AIMessage(
        content="", tool_calls=[{"name": "made_up_tool", "args": {}, "id": "1"}])
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    picked, _, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="anything")], cs=cs))
    assert picked == "M2"


def test_done_falls_back_to_m5(monkeypatch):
    """When everything is confirmed, next_unconfirmed_module returns DONE
    but we don't have a tool for that. v1 routes DONE → END; v2 instead
    runs M5 so the user can still get a reply (e.g. asking to edit a
    chapter after the thesis is 'done'). Regression: don't crash trying
    to look up "DONE" in _AGENT_BY_KEY."""
    cs = ContextStore(**{m: {"confirmed_at": "x"} for m in
                         ("m1_topic", "m2_literature", "m3_design",
                          "m4_analysis", "m5_writing")})
    m5 = _stub_agent(monkeypatch, "M5", msg="post-done reply")

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    # LLM returns no tool_calls → fallback path → next_unconfirmed returns DONE.
    fake_bound.invoke.return_value = AIMessage(content="", tool_calls=[])
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    picked, result, _intent = router_agent.route_turn(_state(
        [HumanMessage(content="edit chapter 3")], cs=cs))
    assert picked == "M5"
    assert result.assistant_message == "post-done reply"
    m5.step.assert_called_once()


def test_build_digest_includes_awaiting_marker():
    """Digest must surface `_awaiting_field` so the LLM (when it does
    fire) knows which module is mid-question. Even though the awaiting
    short-circuit catches this before the LLM call, the digest contract
    is still load-bearing for the future case where multiple modules
    have partial state and the LLM has to pick among them."""
    cs = ContextStore(
        m1_topic={"confirmed_at": "x", "research_title": "AI in education"},
        # conceptual_model (post-2026-06 merge) replaces the prior
        # scale_items example here — scale_items is no longer a field.
        m3_design={"_awaiting_field": "conceptual_model", "design": "PLS-SEM"},
    )
    digest = router_agent._build_digest(_state([], cs=cs))
    assert "M1" in digest and "confirmed" in digest
    assert "M3" in digest and "AWAITING field 'conceptual_model'" in digest
    assert "M2" in digest and "not confirmed" in digest
