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
    # SP6: compile_pdf now requires project_id and uploads to S3; mock s3 + engine.
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    captured = {}
    def fake_compile(sections, output_path, **kw):
        captured["sections"] = sections
        captured["output_path"] = output_path
        Path(output_path).write_bytes(b"%PDF-1.4 fake")
        return output_path
    monkeypatch.setattr(m5_writing, "_compile_pdf_via_engine", fake_compile)
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = compile_pdf.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
        "project_id": "proj-test",
    })
    # SP6: returns s3_key, not local path
    assert out.startswith("projects/proj-test/exports/thesis-")
    assert out.endswith(".pdf")
    assert fake_s3.put_object.call_count == 1


def test_export_docx_writes_artifact(tmp_path, monkeypatch):
    # SP6: export_docx now requires project_id and uploads to S3; mock s3 + engine.
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    def fake_docx(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 docx fake")
        return output_path
    monkeypatch.setattr(m5_writing, "_export_docx_via_engine", fake_docx)
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = export_docx.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
        "project_id": "proj-test",
    })
    # SP6: returns s3_key, not local path
    assert out.startswith("projects/proj-test/exports/thesis-")
    assert out.endswith(".docx")
    assert fake_s3.put_object.call_count == 1


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


def test_s3_from_env_returns_boto3_client(monkeypatch):
    """The factory should return a boto3 S3 client built from env vars."""
    from orchestrator.tools.m5_writing import s3_from_env
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY", "fake-key")
    monkeypatch.setenv("AWS_SECRET_KEY", "fake-secret")
    client = s3_from_env()
    assert hasattr(client, "put_object")
    assert hasattr(client, "generate_presigned_url")


def test_upload_to_s3_writes_correct_key_and_deletes_local(tmp_path, monkeypatch):
    """_upload_to_s3 uploads to projects/{id}/exports/{filename} and deletes local file."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-abc123.docx"
    local.write_bytes(b"fake docx content")

    s3_key = m5_writing._upload_to_s3(
        str(local), project_id="proj-xyz", kind="docx", filename="thesis-abc123.docx",
    )
    assert s3_key == "projects/proj-xyz/exports/thesis-abc123.docx"
    call = fake_s3.put_object.call_args
    assert call.kwargs["Bucket"] == "test-bucket"
    assert call.kwargs["Key"] == "projects/proj-xyz/exports/thesis-abc123.docx"
    assert call.kwargs["ContentType"].startswith("application/vnd.openxmlformats")
    assert call.kwargs["Body"] == b"fake docx content"
    assert not local.exists()  # local file deleted


def test_upload_to_s3_pdf_content_type(tmp_path, monkeypatch):
    """PDF gets the right content type."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-x.pdf"
    local.write_bytes(b"%PDF-1.4")
    m5_writing._upload_to_s3(str(local), "p", "pdf", "thesis-x.pdf")
    assert fake_s3.put_object.call_args.kwargs["ContentType"] == "application/pdf"


def test_compile_pdf_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    def fake_compile_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"%PDF-1.4\nfake")
        return output_path
    monkeypatch.setattr(m5_writing, "_compile_pdf_via_engine", fake_compile_via_engine)

    s3_key = m5_writing.compile_pdf.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert s3_key.startswith("projects/proj-xyz/exports/thesis-")
    assert s3_key.endswith(".pdf")
    assert fake_s3.put_object.call_count == 1


def test_export_docx_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    def fake_export_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 fake docx")
        return output_path
    monkeypatch.setattr(m5_writing, "_export_docx_via_engine", fake_export_via_engine)

    s3_key = m5_writing.export_docx.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert s3_key.startswith("projects/proj-xyz/exports/thesis-")
    assert s3_key.endswith(".docx")


def test_compile_pdf_raises_without_project_id():
    from orchestrator.tools.m5_writing import compile_pdf
    with pytest.raises(ValueError, match="project_id"):
        compile_pdf.invoke({"sections": [], "project_id": ""})


def test_export_docx_raises_without_project_id():
    from orchestrator.tools.m5_writing import export_docx
    with pytest.raises(ValueError, match="project_id"):
        export_docx.invoke({"sections": [], "project_id": ""})


def test_validate_citations_matches_pool():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Bass (1990) found... Later researchers confirmed (Avolio et al., 2009) that..."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
        {"author": "Avolio et al.", "year": 2009, "title": "Trans. leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    # The regex matches "(Author, Year)" — "Bass (1990)" is NOT in that shape;
    # only "(Avolio et al., 2009)" matches.
    assert "Avolio et al., 2009" in cited
    assert uncited == []


def test_validate_citations_flags_uncited():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Some studies (Smith, 2023) claim X. Others (Bass, 1990) agree."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]
    assert uncited == ["Smith, 2023"]


def test_validate_citations_empty_prose():
    from orchestrator.tools.m5_writing import validate_citations
    cited, uncited = validate_citations("", [])
    assert cited == []
    assert uncited == []


def test_validate_citations_deduplicates():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "(Bass, 1990) said X. Later (Bass, 1990) also said Y."
    references = [{"author": "Bass", "year": 1990}]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]  # de-duplicated
