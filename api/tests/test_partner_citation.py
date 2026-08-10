"""Partner citation = resolve + add citations in a .docx, behind the partner
secret.

cite_docx itself is monkeypatched — the real one is a CrossRef round trip per
source and a model call per uncited claim. What is pinned here is the contract:
auth, ownership scoping, the async shape, and that `unresolved`/`marked` reach
the caller. Those two are how a student learns which claims the tool refused to
invent a source for, and a partner that never sees them cannot show them.
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
from app.routers import partner_citation as router_mod
from app.routers import partner_docx

TOKEN = "test-partner-secret"
_DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")

REPORT = {
    "ok": True, "resolved": 31, "unresolved": 4, "weak": 2, "orphans": 5,
    "added": 12, "marked": 3, "linked": 40, "references": 36, "usage": [],
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
        f"/api/v1/partner/citation{path}",
        headers=headers,
        files={"file": ("thesis.docx", io.BytesIO(body), _DOCX_MIME)},
        data=data or None,
    )


def _status(client, run_id, *, token=TOKEN):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post("/api/v1/partner/citation/status",
                       headers=headers, json={"run_id": run_id})


def _run_files(**kw):
    from app.tool_artifacts import RunFiles
    return RunFiles(**kw)


def test_scan_missing_token_is_401(client):
    assert _post(client, "/scan", token=None).status_code == 401


def test_run_missing_token_is_401(client):
    assert _post(client, "", token=None).status_code == 401


def test_status_missing_token_is_401(client):
    assert _status(client, 1, token=None).status_code == 401


def test_scan_rejects_non_docx(client):
    r = client.post(
        "/api/v1/partner/citation/scan",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("t.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert r.status_code == 415


def test_scan_reports_what_would_be_cited_and_charges_nothing(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd
    monkeypatch.setattr(cd, "scan_cite_docx", lambda b: {
        "ok": True, "intext_citations": 88, "distinct_sources": 35,
        "existing_references": 30, "has_reference_section": True,
        "body_paragraphs": 120, "passages": 60,
        # Upstream keys the partner contract does not carry — must not 500.
        "headings": 14, "tables": 6,
    })
    r = _post(client, "/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["distinct_sources"] == 35
    assert body["has_reference_section"] is True

    with Session(get_engine()) as s:
        row = s.scalars(select(ToolRun).where(ToolRun.tool == "scan-cite-docx")).one()
        assert row.surface == "partner" and row.credits_charged == 0


def test_scan_unreadable_reports_not_ok(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd
    monkeypatch.setattr(cd, "scan_cite_docx", lambda b: {"ok": False, "error": "unreadable"})
    body = _post(client, "/scan").json()
    assert body["ok"] is False and body["error"] == "unreadable"


def test_run_reaches_done_and_keeps_the_refusals_visible(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd

    def fake(body, add_missing=True, on_progress=None):
        if on_progress:
            on_progress(35, 35)
        return b"CITED", REPORT

    monkeypatch.setattr(cd, "cite_docx", fake)
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files(
        input_uri="s3://test-bucket/in/thesis.docx",
        output_uri="s3://test-bucket/out/thesis-cited.docx"))
    monkeypatch.setattr(partner_docx, "presign",
                        lambda uri, expires=3600: "https://example.test/signed" if uri else None)

    run_id = _post(client, "").json()["run_id"]
    partner_docx.join_workers()

    body = _status(client, run_id).json()
    assert body["status"] == "done" and body["ok"] is True
    assert body["done"] == 35 and body["total"] == 35
    assert body["docx_url"] == "https://example.test/signed"
    # The two that must never be dropped: claims left marked rather than given
    # an invented source, and sources CrossRef could not resolve.
    assert body["metrics"]["unresolved"] == 4
    assert body["metrics"]["marked"] == 3
    assert body["metrics"]["added"] == 12


def test_add_missing_false_runs_phase_a_only(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd
    seen = {}

    def fake(body, add_missing=True, on_progress=None):
        seen["add_missing"] = add_missing
        return b"OUT", {**REPORT, "added": 0, "marked": 0}

    monkeypatch.setattr(cd, "cite_docx", fake)
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())

    _post(client, "", add_missing="false")
    partner_docx.join_workers()
    assert seen["add_missing"] is False


def test_failed_run_reports_cite_failed(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd
    monkeypatch.setattr(cd, "cite_docx", lambda *a, **k: (
        None, {"ok": False, "error": "cite_failed", "usage": []}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())

    run_id = _post(client, "").json()["run_id"]
    partner_docx.join_workers()
    body = _status(client, run_id).json()
    assert body["status"] == "error" and body["error"] == "cite_failed"


def test_crashing_run_reports_error(client, monkeypatch):
    import orchestrator.tools.cite_docx as cd

    def boom(*a, **k):
        raise RuntimeError("crossref exploded")

    monkeypatch.setattr(cd, "cite_docx", boom)
    run_id = _post(client, "").json()["run_id"]
    partner_docx.join_workers()
    assert _status(client, run_id).json()["status"] == "error"


def test_status_refuses_another_users_run(client):
    from tests.conftest import make_user

    with Session(get_engine()) as s:
        student = make_user(s)
        row = ToolRun(user_id=student.id, surface="web", tool="cite-docx",
                      ok=False, status="running")
        s.add(row)
        s.commit()
        stolen = row.id

    assert _status(client, stolen).status_code == 404
