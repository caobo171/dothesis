"""Walk the full LangGraph through all 5 modules in auto-mode."""
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from unittest.mock import MagicMock

from orchestrator.agents.m1_topic import M1Agent
from orchestrator.agents.m2 import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.graph import build_graph
from orchestrator.state import ContextStore

pytestmark = pytest.mark.integration


# M1, M3, M4, M5 still use the generic ModuleAgent clarification loop.
# M2 is a sub-graph wrapper now; stubbed separately via get_m2_graph.
_M_RESPONSES = {
    M1Agent: '{"research_title":"T","field":"Marketing","research_type":"quantitative","target_population":"p","scope":"s","objectives":["o"],"research_questions":["q"]}',
    M3Agent: '{"paradigm":"quantitative","design":"Regression","tool":"SPSS","sampling_strategy":"convenience","target_sample_size":200,"constructs":[]}',
    M4Agent: '{"data_type_detected":"SPSS","analysis_outline":{"sections":["Descriptive"]},"results":{},"interpretations":{}}',
    M5Agent: '{"sections":[{"name":"intro","text":"..."}],"export_artifacts":[]}',
}


def _stub_all_agents(monkeypatch):
    for cls, response in _M_RESPONSES.items():
        m = MagicMock(); m.invoke.return_value.content = response
        monkeypatch.setattr(cls, "_get_llm", lambda self, _m=m: _m)

    # Stub the M2 sub-graph and DB session so the wrapper completes without
    # hitting LLMs or Postgres.
    fake_subgraph = MagicMock()
    fake_subgraph.invoke.return_value = {
        "current_phase": "DONE",
        "research_state_draft": "synthesis",
        "candidate_gaps": [{"id": "1", "description": "g",
                            "relevance": "High", "supporting_papers": [],
                            "confirmed": True}],
        "selected_gap_ids": ["1"],
        "verified_refs": [],
        "ch2_draft": "d",
        "citation_list": [],
        "research_type": "quantitative",
    }
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent.get_m2_graph",
        lambda interactive: fake_subgraph,
    )
    from contextlib import contextmanager

    @contextmanager
    def _fake_session():
        fake_db = MagicMock()
        fake_db.query.return_value.filter_by.return_value.all.return_value = []
        yield fake_db
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session", _fake_session,
    )


def test_auto_mode_runs_all_5_modules_in_sequence(monkeypatch):
    _stub_all_agents(monkeypatch)
    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    final = graph.invoke({
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "full-auto"}})

    assert final["current_module"] == "DONE"
    cs = final["context_store"]
    for field in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(cs, field) is not None, f"{field} not filled"
        assert getattr(cs, field).get("confirmed_at") is not None
