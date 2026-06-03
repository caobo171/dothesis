"""End-to-end test for the v2 router-agent graph (graph_v2).

Verifies the SSE-equivalent state shape the chat router depends on:
  - `current_module` + `last_tool_called` are stamped on the patch
  - `_module_paused` reflects ModuleStepResult.transition (negated)
  - AIMessage.additional_kwargs["tool_calls_json"] propagates when the
    module emits a widget hint
  - `context_store` is updated with the picked module's slice
  - cold-start short-circuits to M1 without invoking the router LLM
  - extra_messages (M4-style per-step emissions) ride through

Why this exists: the chat router (api/app/routers/chat.py) reads
`payload["last_tool_called"]` for the v2 branch to derive the module tag.
Without an integration test against the real compiled graph + checkpointer,
a future refactor of router_agent_node could silently drop that field and
break the SSE contract — unit tests on route_turn() alone wouldn't catch
it because the state-patch translation happens in graph_v2.router_agent_node.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents import router_agent
from orchestrator.agents.base import ModuleStepResult
from orchestrator.graph_v2 import build_graph_v2
from orchestrator.state import ContextStore

pytestmark = pytest.mark.integration


def _invoke_state(messages, cs=None, thread_id="router-e2e"):
    """Minimal OrchestratorState shape the graph_v2 _seed node expects.

    We don't pre-populate `context_store`/`mode` for the cold-start case so
    the seed node has work to do (proving it still runs in v2)."""
    base = {
        "project_id": None, "thread_id": None,
        "messages": messages, "current_module": "M1",
        "user_intent": None, "pending_confirmations": [],
    }
    if cs is not None:
        base["context_store"] = cs
        base["mode"] = "interactive"
    return base


def _stub_router_llm_no_call(monkeypatch):
    """Sentinel: any router LLM call raises. Used to prove cold-start +
    awaiting-field paths bypass the LLM end-to-end (not just in route_turn
    unit tests)."""
    monkeypatch.setattr(
        router_agent, "_router_llm",
        lambda: (_ for _ in ()).throw(AssertionError("router LLM called")),
    )


def _stub_module(monkeypatch, module_key: str, *, transition: bool,
                 msg: str, context_patch: dict | None = None,
                 tool_calls_json: dict | None = None,
                 extra_messages: list | None = None) -> MagicMock:
    """Replace the singleton ModuleAgent in router_agent._AGENT_BY_KEY with
    a stub that returns a scripted ModuleStepResult. Returns the stub so
    tests can assert on the OrchestratorState the agent received."""
    stub = MagicMock()
    stub.step.return_value = ModuleStepResult(
        assistant_message=msg,
        context_patch=context_patch or {},
        transition=transition,
        needs_user_reply=not transition,
        tool_calls_json=tool_calls_json,
        extra_messages=extra_messages or [],
    )
    monkeypatch.setitem(router_agent._AGENT_BY_KEY, module_key, stub)
    return stub


def test_cold_start_invoke_emits_v2_state_shape(monkeypatch):
    """First turn of a project: no module confirmed → cold-start short-
    circuit picks M1 without an LLM call. The compiled graph must emit a
    final state whose shape matches what api/app/routers/chat.py reads in
    the v2 branch (`last_tool_called`, `current_module`, `_module_paused`).
    """
    _stub_router_llm_no_call(monkeypatch)
    m1 = _stub_module(
        monkeypatch, "M1",
        transition=False,
        msg="What's your research title?",
        context_patch={"_awaiting_field": "research_title"},
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    final = graph.invoke(
        _invoke_state([HumanMessage(content="hello")]),
        config={"configurable": {"thread_id": "cold-start"}},
    )

    # The state-shape contract the SSE adapter depends on.
    assert final["current_module"] == "M1"
    assert final["last_tool_called"] == "M1"
    # _module_paused == not transition; the stub returned transition=False.
    assert final["_module_paused"] is True

    # Module patch landed in the right ContextStore slice (proves
    # router_agent_node uses _MODULE_FIELD correctly).
    assert final["context_store"].m1_topic == {"_awaiting_field": "research_title"}

    # The AIMessage from the module appears in messages (the seed node also
    # didn't drop the original HumanMessage).
    ai_msgs = [m for m in final["messages"] if isinstance(m, AIMessage)]
    assert len(ai_msgs) == 1
    assert ai_msgs[0].content == "What's your research title?"
    # No widget hint configured → no tool_calls_json key (avoids polluting
    # additional_kwargs with empty dicts, matching v1 behavior).
    assert "tool_calls_json" not in ai_msgs[0].additional_kwargs

    m1.step.assert_called_once()


def test_widget_hint_propagates_through_additional_kwargs(monkeypatch):
    """When a module returns tool_calls_json (e.g. M3 design cards), it
    must ride on AIMessage.additional_kwargs so the SSE adapter forwards
    it to the frontend. This is the v1 contract — must hold in v2 too."""
    _stub_router_llm_no_call(monkeypatch)
    widget = {"type": "card_grid", "options": [{"id": "a", "label": "A"}]}
    _stub_module(
        monkeypatch, "M1",
        transition=False,
        msg="Pick one:",
        tool_calls_json=widget,
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    final = graph.invoke(
        _invoke_state([HumanMessage(content="hi")]),
        config={"configurable": {"thread_id": "widget"}},
    )

    ai = next(m for m in final["messages"] if isinstance(m, AIMessage))
    assert ai.additional_kwargs.get("tool_calls_json") == widget


def test_extra_messages_ride_through(monkeypatch):
    """M4 emits per-step execution AIMessages via ModuleStepResult.extra_
    messages. The v1 graph forwards them; v2 must too — chat.py's SSE loop
    iterates over all messages in the update payload."""
    _stub_router_llm_no_call(monkeypatch)
    extras = [AIMessage(content="step 1 done"), AIMessage(content="step 2 done")]
    _stub_module(
        monkeypatch, "M1",
        transition=True,
        msg="all done",
        extra_messages=extras,
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    final = graph.invoke(
        _invoke_state([HumanMessage(content="run it")]),
        config={"configurable": {"thread_id": "extras"}},
    )

    ai_contents = [m.content for m in final["messages"] if isinstance(m, AIMessage)]
    # Order matters: primary assistant_message first, then extras in order.
    assert ai_contents[-3:] == ["all done", "step 1 done", "step 2 done"]


def test_awaiting_field_short_circuits_through_compiled_graph(monkeypatch):
    """End-to-end version of the router unit test: when a slice has
    _awaiting_field set, the compiled graph must dispatch to that module
    without consulting the LLM, even after a prior turn confirmed M1."""
    _stub_router_llm_no_call(monkeypatch)
    cs = ContextStore(
        m1_topic={"confirmed_at": "2026-06-01"},
        m3_design={"_awaiting_field": "design"},
    )
    m3 = _stub_module(
        monkeypatch, "M3",
        transition=False,
        msg="Got it — anything else about the design?",
        context_patch={"design": "PLS-SEM"},
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    final = graph.invoke(
        _invoke_state([HumanMessage(content="PLS-SEM")], cs=cs),
        config={"configurable": {"thread_id": "awaiting"}},
    )

    assert final["last_tool_called"] == "M3"
    assert final["current_module"] == "M3"
    assert final["context_store"].m3_design == {"design": "PLS-SEM"}
    # The pre-existing M1 slice is preserved (router_agent_node copies the
    # ContextStore rather than building a fresh one — otherwise we'd lose
    # all confirmed work whenever a different module takes a turn).
    assert final["context_store"].m1_topic == {"confirmed_at": "2026-06-01"}
    m3.step.assert_called_once()


def test_llm_pick_dispatches_through_compiled_graph(monkeypatch):
    """When neither short-circuit applies, the router LLM picks a module-
    tool; the compiled graph must dispatch to the matching agent and emit
    the v2 state shape (proves bind_tools → tool_calls → _AGENT_BY_KEY
    chain works inside the LangGraph node, not just in route_turn)."""
    cs = ContextStore(m1_topic={"confirmed_at": "2026-06-01"})

    fake_llm = MagicMock()
    fake_bound = MagicMock()
    fake_bound.invoke.return_value = AIMessage(
        content="",
        tool_calls=[{"name": "m4_analysis_step",
                     "args": {"user_intent": "run analysis"}, "id": "1"}],
    )
    fake_llm.bind_tools.return_value = fake_bound
    monkeypatch.setattr(router_agent, "_router_llm", lambda: fake_llm)

    m4 = _stub_module(
        monkeypatch, "M4",
        transition=False,
        msg="Sure — what data do you have?",
        context_patch={"_awaiting_field": "data_type"},
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    final = graph.invoke(
        _invoke_state([HumanMessage(content="run my analysis")], cs=cs),
        config={"configurable": {"thread_id": "llm-pick"}},
    )

    assert final["last_tool_called"] == "M4"
    assert final["current_module"] == "M4"
    m4.step.assert_called_once()
    # tool_choice="any" is what forces a tool call — assert we bound it so
    # a regression that drops it (and lets Gemini reply in prose) fails here.
    bind_kwargs = fake_llm.bind_tools.call_args.kwargs
    assert bind_kwargs.get("tool_choice") == "any"


def test_checkpointer_persists_state_across_turns(monkeypatch):
    """Two-turn replay: turn 1 cold-starts to M1 and parks awaiting a field;
    turn 2 reuses the same thread_id and MUST resume against the persisted
    ContextStore (so the awaiting-field short-circuit fires on turn 2).

    Catches the regression class where a router refactor accidentally
    drops `context_store` from the patch — unit tests on route_turn would
    pass but the next turn would see a fresh ContextStore and re-cold-start.
    """
    _stub_router_llm_no_call(monkeypatch)
    m1 = _stub_module(
        monkeypatch, "M1",
        transition=False,
        msg="What's your title?",
        context_patch={"_awaiting_field": "research_title"},
    )

    graph = build_graph_v2(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "two-turns"}}

    # Turn 1.
    graph.invoke(_invoke_state([HumanMessage(content="hi")]), config=cfg)
    assert m1.step.call_count == 1

    # Turn 2: send only the new user message; the checkpointer replays the
    # accumulated messages + context_store. Awaiting-field short-circuit
    # should fire (still no LLM call — _stub_router_llm_no_call asserts).
    m1.step.return_value = ModuleStepResult(
        assistant_message="Confirmed M1.",
        context_patch={"research_title": "X",
                       "confirmed_at": "2026-06-02"},
        transition=True,
        needs_user_reply=False,
    )
    final = graph.invoke(
        {"messages": [HumanMessage(content="my title is X")]},
        config=cfg,
    )

    assert m1.step.call_count == 2
    # Slice now confirmed; _awaiting_field cleared via the new context_patch.
    assert final["context_store"].m1_topic.get("confirmed_at") == "2026-06-02"
    assert "_awaiting_field" not in final["context_store"].m1_topic
    assert final["_module_paused"] is False  # transition=True → not paused
