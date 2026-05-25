from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m5_writing import (
    compile_pdf, compose_section, export_docx, format_citations, validate_draft,
)


def test_compose_section_uses_engine_compose(monkeypatch):
    fake_compose = MagicMock(return_value="Chapter 2: Literature Review draft...")
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._compose_section_via_engine", fake_compose
    )
    out = compose_section.invoke({
        "section_name": "lit_review",
        "context_store": {
            "m1_topic": {"research_title": "X"},
            "m2_literature": {"research_gaps": [{"description": "..."}]},
        },
    })
    assert "Chapter" in out
    fake_compose.assert_called_once()


def test_validate_draft_returns_ok_when_no_issues(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._validate_via_engine",
        lambda text: {"issues": [], "score": 0.95},
    )
    out = validate_draft.invoke({"text": "This is the draft."})
    assert out["score"] == 0.95
    assert out["issues"] == []


def test_compile_pdf_writes_artifact(tmp_path, monkeypatch):
    captured = {}
    def fake_compile(sections, output_path, **kw):
        captured["sections"] = sections
        captured["output_path"] = output_path
        Path(output_path).write_bytes(b"%PDF-1.4 fake")
        return output_path
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._compile_pdf_via_engine", fake_compile
    )
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = compile_pdf.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
    })
    assert out.endswith(".pdf")
    assert Path(out).exists()


def test_export_docx_writes_artifact(tmp_path, monkeypatch):
    def fake_docx(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 docx fake")
        return output_path
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._export_docx_via_engine", fake_docx
    )
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))
    out = export_docx.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
    })
    assert out.endswith(".docx")
    assert Path(out).exists()


def test_format_citations_apa(monkeypatch):
    fake = MagicMock()
    fake.compile.return_value = "Wang, X. (2011). Title."
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing.CitationCompiler", lambda style: fake
    )
    out = format_citations.invoke({
        "items": [{"author": "Wang", "year": 2011, "title": "Title"}],
        "style": "apa7",
    })
    assert "Wang" in out
