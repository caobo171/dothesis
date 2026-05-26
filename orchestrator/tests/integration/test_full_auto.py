"""Verify auto-mode's end state contains export artifacts."""
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


def test_auto_mode_produces_docx_and_pdf_uris(monkeypatch, tmp_path):
    # M1, M3, M4, M5 still use the ModuleAgent generic clarification loop —
    # monkeypatch their _get_llm to return stub JSON.
    responses = {
        M1Agent: '{"research_title":"T","field":"Marketing","research_type":"quantitative","target_population":"p","scope":"s","objectives":["o"],"research_questions":["q"]}',
        M3Agent: '{"paradigm":"quantitative","design":"Regression","tool":"SPSS","sampling_strategy":"convenience","target_sample_size":200,"constructs":[]}',
        M4Agent: '{"data_type_detected":"SPSS","analysis_outline":{"sections":["Descriptive"]},"results":{},"interpretations":{}}',
        M5Agent: (
            '{"sections":[{"name":"intro","text":"..."}],'
            '"export_artifacts":['
            f'{{"kind":"docx","uri":"{tmp_path}/thesis.docx","size_bytes":1024}},'
            f'{{"kind":"pdf","uri":"{tmp_path}/thesis.pdf","size_bytes":2048}}'
            ']}'
        ),
    }
    for cls, blob in responses.items():
        m = MagicMock(); m.invoke.return_value.content = blob
        monkeypatch.setattr(cls, "_get_llm", lambda self, _m=m: _m)

    # M2 is now a sub-graph wrapper — monkeypatch get_m2_graph + the DB session
    # opener so the wrapper produces a DONE final state without hitting LLMs or DB.
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

    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    final = graph.invoke({
        "messages": [HumanMessage(content="topic")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "auto-export"}})

    arts = final["context_store"].m5_writing["export_artifacts"]
    kinds = {a["kind"] for a in arts}
    assert kinds == {"docx", "pdf"}
