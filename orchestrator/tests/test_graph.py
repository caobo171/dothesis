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
    """Inject fake LLMs so all 5 module agents auto-fill silently and return valid schemas."""
    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.agents.m2_literature import M2Agent
    from orchestrator.agents.m3_design import M3Agent
    from orchestrator.agents.m4_analysis import M4Agent
    from orchestrator.agents.m5_writing import M5Agent

    responses = {
        M1Agent: '{"research_title": "T", "field": "Marketing", "research_type": "quantitative", "target_population": "p", "scope": "s", "objectives": ["o1"], "research_questions": ["q1"]}',
        M2Agent: '{"research_state_summary":"x","research_gaps":[{"description":"g","relevance":"High","confirmed":true,"supporting_papers":[]}],"theoretical_framework":"f","hypotheses":[],"literature_review_doc":"d","citation_list":[]}',
        M3Agent: '{"paradigm":"quantitative","design":"Regression","tool":"SPSS","sampling_strategy":"convenience","target_sample_size":200,"constructs":[]}',
        M4Agent: '{"data_type_detected":"SPSS","analysis_outline":{"sections":["Descriptive"]},"results":{},"interpretations":{}}',
        M5Agent: '{"sections":[{"name":"intro","text":"..."}],"export_artifacts":[]}',
    }
    for cls, blob in responses.items():
        m = MagicMock(); m.invoke.return_value.content = blob
        monkeypatch.setattr(cls, "_get_llm", lambda self, _m=m: _m)

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
