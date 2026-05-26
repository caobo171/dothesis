"""Tests for the LangGraph topology — uses an in-memory checkpointer + fake LLMs."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.graph import build_graph
from orchestrator.state import ContextStore


def _all_modules_confirmed_cs():
    return ContextStore(**{m: {"confirmed_at": "2026-05-26"} for m in
                           ("m1_topic", "m2_literature", "m3_design",
                            "m4_analysis", "m5_writing")})


def test_graph_compiles_in_both_modes():
    g_interactive = build_graph(interactive=True, checkpointer=MemorySaver())
    g_auto       = build_graph(interactive=False, checkpointer=MemorySaver())
    assert g_interactive is not None
    assert g_auto is not None


def test_graph_terminates_when_all_confirmed():
    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    state = {
        "messages": [HumanMessage(content="seed")],
        "current_module": "M1",
        "context_store": _all_modules_confirmed_cs(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    config = {"configurable": {"thread_id": "test-1"}}
    final = graph.invoke(state, config=config)
    assert final["current_module"] == "DONE"


def test_graph_routes_to_correct_first_unconfirmed(monkeypatch):
    """Inject fake LLMs/sub-graphs so all 5 module agents complete silently."""
    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.agents.m2 import M2Agent
    from orchestrator.agents.m3_design import M3Agent
    from orchestrator.agents.m4_analysis import M4Agent
    from orchestrator.agents.m5_writing import M5Agent

    # M1, M3-M5 use the generic _get_llm auto-fill path.
    llm_responses = {
        M1Agent: '{"research_title": "T", "field": "Marketing", "research_type": "quantitative", "target_population": "p", "scope": "s", "objectives": ["o1"], "research_questions": ["q1"]}',
        M3Agent: '{"paradigm":"quantitative","design":"Regression","tool":"SPSS","sampling_strategy":"convenience","target_sample_size":200,"constructs":[]}',
        M4Agent: '{"data_type_detected":"SPSS","analysis_outline":{"sections":["Descriptive"]},"results":{},"interpretations":{}}',
        M5Agent: '{"sections":[{"name":"intro","text":"..."}],"export_artifacts":[]}',
    }
    for cls, blob in llm_responses.items():
        m = MagicMock(); m.invoke.return_value.content = blob
        monkeypatch.setattr(cls, "_get_llm", lambda self, _m=m: _m)

    # M2 now delegates to the sub-graph; stub get_m2_graph and the DB session.
    fake_m2_subgraph = MagicMock()
    fake_m2_subgraph.invoke.return_value = {
        "current_phase": "DONE",
        "research_state_draft": "x",
        "candidate_gaps": [{"description": "g", "supporting_papers": []}],
        "selected_gap_ids": ["0"],
        "ch2_draft": "d",
        "citation_list": [],
        "research_type": "quantitative",
    }
    monkeypatch.setattr("orchestrator.agents.m2.agent.get_m2_graph",
                        lambda interactive: fake_m2_subgraph)

    class _FakeDb:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def query(self, *a, **kw):
            m = MagicMock()
            m.filter_by.return_value.all.return_value = []
            return m
    monkeypatch.setattr("orchestrator.agents.m2.agent._open_db_session", lambda: _FakeDb())

    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    final = graph.invoke({
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "test-flow"}})

    assert final["current_module"] == "DONE"
    for m in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(final["context_store"], m) is not None


def test_graph_node_attaches_tool_calls_json_to_ai_message(monkeypatch):
    """When ModuleStepResult.tool_calls_json is set, the emitted AIMessage
    should carry the same dict in additional_kwargs['tool_calls_json']."""
    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.agents.base import ModuleStepResult

    hint = {"widget_type": "card_grid", "field_name": "field",
            "title": "Pick", "options": [], "columns": 3}

    def fake_step(self, state):
        return ModuleStepResult(
            assistant_message="Pick a field",
            context_patch={"field": None, "confirmed_at": "2026-05-26"},
            transition=False, needs_user_reply=True,
            tool_calls_json=hint,
        )
    monkeypatch.setattr(M1Agent, "step", fake_step)

    # Build the graph in NON-interactive (no interrupts) so the first invoke
    # actually executes the M1 spoke. Agent mode in state is still "interactive"
    # so the agent's interactive branch is exercised.
    graph = build_graph(interactive=False, checkpointer=MemorySaver())

    # Pre-confirm M2-M5 so the supervisor routes to M1, then on the loop-back
    # routes straight to DONE — keeps the test focused on the M1 node.
    cs = ContextStore(**{
        m: {"confirmed_at": "2026-05-26"}
        for m in ("m2_literature", "m3_design", "m4_analysis", "m5_writing")
    })

    config = {"configurable": {"thread_id": "test-tc"}}
    final = graph.invoke({
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": cs,
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }, config=config)

    last_ai = next(
        m for m in reversed(final["messages"])
        if m.__class__.__name__ == "AIMessage"
    )
    assert last_ai.additional_kwargs.get("tool_calls_json") == hint
