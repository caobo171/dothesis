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

    # M5's auto-compose path calls the tools-module compose_chapter (its own LLM,
    # not the agent's _get_llm) and run_export (S3). Stub both so M5 completes
    # silently and offline — the test is about ROUTING, not real chapter writing.
    import orchestrator.agents.m5_writing as _m5agent
    monkeypatch.setattr(_m5agent, "compose_chapter", MagicMock(
        invoke=lambda kw: {"name": kw.get("chapter_name", "intro"),
                           "prose": "stub", "citations_used": [], "uncited_warnings": []}))
    monkeypatch.setattr(_m5agent, "run_export", lambda sections, project_id, **kw: [
        {"kind": "docx", "s3_key": f"projects/{project_id}/exports/x.docx",
         "download_url": f"/api/v1/projects/{project_id}/exports/x.docx", "size_bytes": 1},
        {"kind": "pdf", "s3_key": f"projects/{project_id}/exports/x.pdf",
         "download_url": f"/api/v1/projects/{project_id}/exports/x.pdf", "size_bytes": 1}])

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


def test_graph_pauses_when_module_pauses_without_awaiting_markers(monkeypatch):
    """Regression: a module that pauses for user input via transition=False but
    does NOT set the base-loop _awaiting_field/_awaiting_confirm markers (e.g.
    M2, whose phase state lives in its own keys) must still pause — route to END.

    Before the fix, _make_route_after_module detected "module paused" only by
    sniffing _awaiting_* markers in the context slice, so M2 looked "finished"
    and the graph looped supervisor↔module until GraphRecursionError, which the
    chat router swallowed → the user saw no reply and was stuck forever.
    The route now keys off the universal ModuleStepResult.transition contract.
    """
    from orchestrator.agents.base import ModuleStepResult
    from orchestrator.agents.m1_topic import M1Agent

    def fake_step(self, state):
        # Mimics M2's pause: a question, no _awaiting_* markers, no confirmed_at.
        return ModuleStepResult(
            assistant_message="Do you have papers to upload?",
            context_patch={"current_phase": "familiarize"},
            transition=False, needs_user_reply=True,
        )
    monkeypatch.setattr(M1Agent, "step", fake_step)

    # Pre-confirm M2-M5 so the supervisor routes straight to M1.
    cs = ContextStore(**{
        m: {"confirmed_at": "2026-05-26"}
        for m in ("m2_literature", "m3_design", "m4_analysis", "m5_writing")
    })
    g = build_graph(interactive=True, checkpointer=MemorySaver())
    # Low recursion_limit so a routing loop surfaces as GraphRecursionError fast.
    final = g.invoke({
        "messages": [HumanMessage(content="hi")],
        "current_module": "M1",
        "context_store": cs,
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "pause-no-markers"},
               "recursion_limit": 8})

    ai = [m for m in final["messages"] if m.__class__.__name__ == "AIMessage"]
    assert any("papers" in m.content.lower() for m in ai)


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


def test_graph_node_emits_extra_messages_from_step_result(monkeypatch):
    """When ModuleStepResult.extra_messages is non-empty, the graph node
    emits the primary AIMessage followed by each extra message in order."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.base import ModuleStepResult
    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.graph import build_graph
    from orchestrator.state import ContextStore

    extra1 = AIMessage(content="step 1 result")
    extra2 = AIMessage(content="step 2 result")

    def fake_step(self, state):
        return ModuleStepResult(
            assistant_message="primary",
            context_patch={"confirmed_at": "2026-05-27"},
            transition=False, needs_user_reply=True,
            extra_messages=[extra1, extra2],
        )
    monkeypatch.setattr(M1Agent, "step", fake_step)

    cs = ContextStore(**{
        m: {"confirmed_at": "2026-05-26"}
        for m in ("m2_literature", "m3_design", "m4_analysis", "m5_writing")
    })
    g = build_graph(interactive=False, checkpointer=MemorySaver())
    final = g.invoke({
        "messages": [HumanMessage(content="start")],
        "current_module": "M1",
        "context_store": cs,
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "test-extra-msgs"}})

    ai_msgs = [m for m in final["messages"] if m.__class__.__name__ == "AIMessage"]
    contents = [m.content for m in ai_msgs]
    # The primary message + both extras must appear in order.
    assert "primary" in contents
    assert "step 1 result" in contents
    assert "step 2 result" in contents
    primary_idx = contents.index("primary")
    s1_idx = contents.index("step 1 result")
    s2_idx = contents.index("step 2 result")
    assert primary_idx < s1_idx < s2_idx
