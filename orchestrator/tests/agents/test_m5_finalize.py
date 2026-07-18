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


def _fake_run_export(pid: str):
    """Mimic orchestrator.tools.m5_writing.run_export: returns the artifact-dict
    list (docx + pdf) the agent maps into ExportArtifacts — WITHOUT touching S3.
    The agent now routes exports through run_export, so that is the seam to mock
    (the old per-tool export_docx/compile_pdf mocks were dead after that refactor)."""
    def _f(sections, project_id, **kwargs):
        return [
            {"kind": "docx", "s3_key": f"projects/{pid}/exports/thesis-abc.docx",
             "download_url": f"/api/v1/projects/{pid}/exports/thesis-abc.docx", "size_bytes": 1024},
            {"kind": "pdf", "s3_key": f"projects/{pid}/exports/thesis-abc.pdf",
             "download_url": f"/api/v1/projects/{pid}/exports/thesis-abc.pdf", "size_bytes": 2048},
        ]
    return _f


def test_finalize_calls_export_tools_and_transitions(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod
    captured = {}

    def _run_export(sections, project_id, **kwargs):
        captured["project_id"] = project_id
        return _fake_run_export("proj-xyz")(sections, project_id, **kwargs)
    monkeypatch.setattr(m5_mod, "run_export", _run_export)

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

    # export routed through run_export with the project_id
    assert captured["project_id"] == "proj-xyz"

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
    monkeypatch.setattr(m5_mod, "run_export", lambda sections, project_id, **kw: [
        {"kind": "docx", "s3_key": "projects/p/exports/x.docx",
         "download_url": "/api/v1/projects/p/exports/x.docx", "size_bytes": 100},
        {"kind": "pdf", "s3_key": "projects/p/exports/x.pdf",
         "download_url": "/api/v1/projects/p/exports/x.pdf", "size_bytes": 200}])

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
