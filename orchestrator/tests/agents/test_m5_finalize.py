"""Tests for M5Agent _finalize_and_export — confirm + export + transition."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def _build_full_partial():
    """A post-compose partial with all 6 chapters drafted."""
    chapters = {n: {"name": n, "prose": f"# {n}\nContent"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    return {
        "chapters": chapters,
        "bibliography": "Bass, A. (1990). Leadership.",
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }


def test_finalize_calls_export_tools_and_transitions(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod

    # Tools now return {s3_key, size_bytes} dicts — not plain strings.
    fake_docx = MagicMock()
    fake_docx.invoke.return_value = {"s3_key": "projects/proj-xyz/exports/thesis-abc.docx", "size_bytes": 1024}
    monkeypatch.setattr(m5_mod, "export_docx", fake_docx)

    fake_pdf = MagicMock()
    fake_pdf.invoke.return_value = {"s3_key": "projects/proj-xyz/exports/thesis-abc.pdf", "size_bytes": 2048}
    monkeypatch.setattr(m5_mod, "compile_pdf", fake_pdf)

    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5", "project_id": "proj-xyz",
        "context_store": ContextStore(
            m1_topic={"research_title": "x", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "x"},
            m5_writing=partial,
        ),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)

    # Both tools called with project_id
    assert fake_docx.invoke.called
    assert fake_pdf.invoke.called
    docx_call = fake_docx.invoke.call_args.args[0]
    assert docx_call["project_id"] == "proj-xyz"

    # export_artifacts populated
    artifacts = result.context_patch["export_artifacts"]
    assert len(artifacts) == 2
    kinds = {a["kind"] for a in artifacts}
    assert kinds == {"docx", "pdf"}
    docx_artifact = next(a for a in artifacts if a["kind"] == "docx")
    assert docx_artifact["s3_key"] == "projects/proj-xyz/exports/thesis-abc.docx"
    assert "thesis-abc.docx" in docx_artifact["download_url"]

    # confirmed_at stamped + transition=True
    assert result.context_patch["confirmed_at"] is not None
    assert result.transition is True


def test_finalize_emits_markdown_links(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod
    # Tools now return {s3_key, size_bytes} dicts — not plain strings.
    monkeypatch.setattr(m5_mod, "export_docx", MagicMock(invoke=lambda kw: {"s3_key": "projects/p/exports/x.docx", "size_bytes": 100}))
    monkeypatch.setattr(m5_mod, "compile_pdf", MagicMock(invoke=lambda kw: {"s3_key": "projects/p/exports/x.pdf", "size_bytes": 200}))

    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(m5_writing=partial),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)
    assert "Download" in result.assistant_message
    assert "/api/v1/projects/p/exports/x.docx" in result.assistant_message
    assert "/api/v1/projects/p/exports/x.pdf" in result.assistant_message


def test_finalize_raises_without_project_id():
    """No project_id in state → finalize raises with clear message."""
    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5",
        "project_id": "",  # explicitly empty
        "context_store": ContextStore(m5_writing=partial),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    with pytest.raises(RuntimeError, match="project_id"):
        agent.step(state)
