"""Partner similarity = the .docx self-check behind the shared partner secret.

The check itself is monkeypatched; what is under test is the contract around it
— auth, and above all that `corpus_checked` reaches the caller intact. A
partner that renders "nobody looked" as "nothing found" tells a student their
thesis is clean when no index was ever searched, so every response carries the
field and these tests pin it.
"""
from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ToolRun
from app.routers import partner_similarity as router_mod

TOKEN = "test-partner-secret"
_DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")

COUNTS = {
    "body_paragraphs": 120, "reference_entries": 40, "flagged_paragraphs": 7,
    "internal_duplication": 3, "uncited_quotations": 2,
    "cited_not_in_references": 1, "references_never_cited": 4,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    from app.settings import reset_settings
    reset_settings()
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    return TestClient(app)


def _post(client, path, *, token=TOKEN, body=b"PK\x03\x04 fake docx", **data):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post(
        f"/api/v1/partner/similarity{path}",
        headers=headers,
        files={"file": ("thesis.docx", io.BytesIO(body), _DOCX_MIME)},
        data=data or None,
    )


def _run_files(**kw):
    from app.tool_artifacts import RunFiles
    return RunFiles(**kw)


def test_scan_missing_token_is_401(client):
    assert _post(client, "/scan", token=None).status_code == 401


def test_run_missing_token_is_401(client):
    assert _post(client, "", token=None).status_code == 401


def test_scan_rejects_non_docx(client):
    r = client.post(
        "/api/v1/partner/similarity/scan",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("t.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert r.status_code == 415


def test_scan_reports_no_corpus_and_charges_nothing(client, monkeypatch):
    import orchestrator.tools.similarity_docx as sd
    import orchestrator.tools.plagiarism as pl
    monkeypatch.setattr(sd, "scan_docx", lambda b: {
        "ok": True, "paragraphs": 300, "body_paragraphs": 120, "words": 17000,
        "quotations": 12, "in_text_citations": 88, "reference_entries": 40,
    })
    monkeypatch.setattr(pl, "get_provider", lambda: None)
    r = _post(client, "/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["words"] == 17000
    # The quote has to carry this, not just the result — a partner prices and
    # words its UI before the run, not after.
    assert body["corpus_available"] is False

    with Session(get_engine()) as s:
        row = s.scalars(select(ToolRun).where(ToolRun.tool == "scan-similarity-docx")).one()
        assert row.surface == "partner" and row.credits_charged == 0


def test_run_without_provider_says_nobody_looked(client, monkeypatch):
    import orchestrator.tools.similarity_docx as sd
    import orchestrator.tools.plagiarism as pl
    monkeypatch.setattr(pl, "get_provider", lambda: None)
    monkeypatch.setattr(sd, "similarity_docx", lambda body, **kw: (
        b"ANNOTATED", {"ok": True, "corpus_checked": False, "corpus_error": None,
                       "counts": COUNTS}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files(
        input_uri="s3://test-bucket/in/thesis.docx",
        output_uri="s3://test-bucket/out/thesis-similarity.docx"))
    monkeypatch.setattr(router_mod, "_presign", lambda uri, expires=3600: "https://example.test/signed")

    body = _post(client, "", language="vi").json()
    assert body["ok"] is True
    # The whole point: an unconfigured deployment must not read as a clean bill.
    assert body["corpus_checked"] is False
    assert body["counts"]["flagged_paragraphs"] == 7
    assert body["docx_url"] == "https://example.test/signed"
    assert body["docx_uri"] == "s3://test-bucket/out/thesis-similarity.docx"


def test_run_charges_the_offline_rate_when_no_provider_ran(client, monkeypatch):
    import orchestrator.tools.similarity_docx as sd
    import orchestrator.tools.plagiarism as pl
    monkeypatch.setattr(pl, "get_provider", lambda: None)
    monkeypatch.setattr(sd, "similarity_docx", lambda body, **kw: (
        b"OUT", {"ok": True, "corpus_checked": False, "counts": COUNTS}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())
    monkeypatch.setattr(router_mod, "_presign", lambda uri, expires=3600: None)

    _post(client, "")
    with Session(get_engine()) as s:
        row = s.scalars(select(ToolRun).where(ToolRun.tool == "similarity-docx")).one()
        assert row.surface == "partner"
        # Billed as the offline half, never the corpus rate it did not perform.
        assert s.scalars(select(ToolRun).where(
            ToolRun.tool == "similarity-docx-corpus")).all() == []


def test_run_charges_the_corpus_rate_when_a_provider_ran(client, monkeypatch):
    import orchestrator.tools.similarity_docx as sd
    import orchestrator.tools.plagiarism as pl

    class FakeProvider:
        name = "fake"

    monkeypatch.setattr(pl, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(sd, "similarity_docx", lambda body, **kw: (
        b"OUT", {"ok": True, "corpus_checked": True, "counts": COUNTS}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())
    monkeypatch.setattr(router_mod, "_presign", lambda uri, expires=3600: None)

    assert _post(client, "").json()["corpus_checked"] is True
    with Session(get_engine()) as s:
        assert s.scalars(select(ToolRun).where(
            ToolRun.tool == "similarity-docx-corpus")).one() is not None


def test_unreadable_document_is_422(client, monkeypatch):
    import orchestrator.tools.similarity_docx as sd
    import orchestrator.tools.plagiarism as pl
    monkeypatch.setattr(pl, "get_provider", lambda: None)
    monkeypatch.setattr(sd, "similarity_docx", lambda body, **kw: (
        None, {"ok": False, "error": "unreadable"}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())

    r = _post(client, "")
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "unreadable"
