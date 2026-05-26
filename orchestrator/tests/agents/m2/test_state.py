"""Tests for M2SubGraphState shape and helpers."""
from langchain_core.messages import HumanMessage
from orchestrator.agents.m2.state import M2SubGraphState, fresh_state


def test_fresh_state_has_defaults():
    s = fresh_state(
        project_id="00000000-0000-0000-0000-000000000001",
        thread_id="00000000-0000-0000-0000-000000000002",
        research_title="X",
        research_type="quantitative",
        language="en",
        paper_uris=["s3://b/k.pdf"],
        mode="interactive",
    )
    assert s["current_phase"] == "familiarize"
    assert s["regeneration_count"] == {}
    assert s["paper_uris"] == ["s3://b/k.pdf"]
    assert s["has_uploaded_papers"] is None
    assert s["research_state_confirmed"] is False
    assert s["page_check_cursor"] == 0


def test_fresh_state_empty_paper_uris():
    s = fresh_state(
        project_id="x", thread_id="y", research_title="T",
        research_type="qualitative", language="vi",
        paper_uris=[], mode="auto",
    )
    assert s["paper_uris"] == []
    assert s["language"] == "vi"


def test_build_m2_subgraph_compiles_with_stubs():
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.m2.graph import build_m2_subgraph
    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    assert g is not None


def test_m2_subgraph_auto_mode_walks_to_done():
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.m2.graph import build_m2_subgraph
    from orchestrator.agents.m2.state import fresh_state

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(
        project_id="00000000-0000-0000-0000-000000000001",
        thread_id="00000000-0000-0000-0000-000000000002",
        research_title="X", research_type="quantitative",
        language="en", paper_uris=[], mode="auto",
    )
    final = g.invoke(s, config={"configurable": {"thread_id": "t1::m2"}})
    assert final["current_phase"] == "DONE"
