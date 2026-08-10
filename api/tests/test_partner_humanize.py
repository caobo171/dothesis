"""Partner humanize = the .docx rewrite reachable with the shared partner
secret instead of a student's session.

The walk itself is monkeypatched throughout — the real one is ~70 sequential
model calls and tens of minutes, so what is under test here is the contract
around it: auth, ownership scoping, the async start/poll shape, and what a
crashed or stalled run reports.
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
from app.routers import partner_docx, partner_humanize as router_mod

TOKEN = "test-partner-secret"
_DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    from app.settings import reset_settings
    reset_settings()
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    return TestClient(app)


def _scan(client, *, token=TOKEN, body=b"PK\x03\x04 fake docx"):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post(
        "/api/v1/partner/humanize/scan",
        headers=headers,
        files={"file": ("thesis.docx", io.BytesIO(body), _DOCX_MIME)},
    )


def test_scan_missing_token_is_401(client):
    assert _scan(client, token=None).status_code == 401


def test_scan_wrong_token_is_401(client):
    assert _scan(client, token="nope").status_code == 401


def test_scan_rejects_non_docx(client):
    r = client.post(
        "/api/v1/partner/humanize/scan",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("thesis.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert r.status_code == 415
    assert r.json()["detail"]["error"]["code"] == "docx_only"


def test_scan_returns_counts_and_charges_nothing(client, monkeypatch):
    import orchestrator.tools.humanize_docx as hd
    monkeypatch.setattr(hd, "scan_docx", lambda b: {
        "ok": True, "body_paragraphs": 132, "headings": 14,
        "short_or_captions": 20, "tables": 6, "passages": 70, "chars": 86_400,
        "words": 17_000,
    })
    r = _scan(client)
    assert r.status_code == 200
    assert r.json()["chars"] == 86_400
    # The count partners price on — it must survive the response model.
    assert r.json()["words"] == 17_000
    assert r.json()["body_paragraphs"] == 132

    with Session(get_engine()) as s:
        row = s.scalars(select(ToolRun).where(ToolRun.tool == "scan-docx")).one()
        assert row.surface == "partner"
        assert row.credits_charged == 0


def test_scan_unreadable_docx_reports_not_ok(client, monkeypatch):
    import orchestrator.tools.humanize_docx as hd
    monkeypatch.setattr(hd, "scan_docx", lambda b: {"ok": False, "error": "unreadable"})
    r = _scan(client)
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "unreadable"


# --- the run itself ---------------------------------------------------------

def _start(client, *, token=TOKEN, body=b"PK\x03\x04 fake docx", **data):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post(
        "/api/v1/partner/humanize",
        headers=headers,
        files={"file": ("thesis.docx", io.BytesIO(body), _DOCX_MIME)},
        data=data or None,
    )


def _status(client, run_id, *, token=TOKEN):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post("/api/v1/partner/humanize/status",
                       headers=headers, json={"run_id": run_id})


def _run_files(**kw):
    from app.tool_artifacts import RunFiles
    return RunFiles(**kw)


def test_run_missing_token_is_401(client):
    assert _start(client, token=None).status_code == 401


def test_run_rejects_non_docx(client):
    r = client.post(
        "/api/v1/partner/humanize",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("thesis.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert r.status_code == 415


def test_run_reaches_done_with_url_and_metrics(client, monkeypatch):
    import orchestrator.tools.humanize_docx as hd

    def fake_walk(body, language=None, user_anchor=None, on_progress=None):
        if on_progress:
            on_progress(70, 70)
        return b"OUT", {"ok": True, "rewritten": 80, "skipped": 52,
                        "declined": 40, "coverage": 0.606, "usage": []}

    monkeypatch.setattr(hd, "humanize_docx", fake_walk)
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files(
        input_uri="s3://test-bucket/in/thesis.docx",
        output_uri="s3://test-bucket/out/thesis-humanized.docx"))
    monkeypatch.setattr(partner_docx, "presign",
                        lambda uri, expires=3600: "https://example.test/signed" if uri else None)

    started = _start(client, language="vi")
    assert started.status_code == 200
    run_id = started.json()["run_id"]
    assert started.json()["status"] == "processing"

    partner_docx.join_workers()

    body = _status(client, run_id).json()
    assert body["status"] == "done"
    assert body["ok"] is True
    assert body["done"] == 70 and body["total"] == 70
    assert body["docx_url"] == "https://example.test/signed"
    assert body["metrics"]["rewritten"] == 80
    assert body["filename"] == "thesis.docx"


def test_failed_walk_reports_error(client, monkeypatch):
    import orchestrator.tools.humanize_docx as hd
    monkeypatch.setattr(hd, "humanize_docx", lambda *a, **k: (
        None, {"ok": False, "error": "rewrite_failed", "usage": []}))
    monkeypatch.setattr(router_mod, "store_run_files", lambda **kw: _run_files())

    run_id = _start(client).json()["run_id"]
    partner_docx.join_workers()
    body = _status(client, run_id).json()
    assert body["status"] == "error"
    assert body["error"] == "rewrite_failed"
    assert body["docx_url"] is None


def test_crashing_walk_reports_error(client, monkeypatch):
    import orchestrator.tools.humanize_docx as hd

    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(hd, "humanize_docx", boom)
    run_id = _start(client).json()["run_id"]
    partner_docx.join_workers()
    assert _status(client, run_id).json()["status"] == "error"


def test_status_refuses_a_non_partner_run(client):
    """A run owned by a real student is invisible to a partner token."""
    from tests.conftest import make_user

    with Session(get_engine()) as s:
        student = make_user(s)
        row = ToolRun(user_id=student.id, surface="web", tool="humanize-docx",
                      ok=False, status="running")
        s.add(row)
        s.commit()
        stolen = row.id

    assert _status(client, stolen).status_code == 404


def test_status_needs_the_partner_token(client):
    assert _status(client, 1, token=None).status_code == 401


def test_stale_running_run_is_reported_lost(client, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(router_mod, "start_worker", lambda *a, **k: None)
    run_id = _start(client).json()["run_id"]
    with Session(get_engine()) as s:
        row = s.get(ToolRun, run_id)
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=91)
        s.commit()

    body = _status(client, run_id).json()
    assert body["status"] == "error"
    assert body["error"] == "run_lost"


def test_running_run_reports_progress(client, monkeypatch):
    monkeypatch.setattr(router_mod, "start_worker", lambda *a, **k: None)
    run_id = _start(client).json()["run_id"]
    from app.tool_billing import bump_progress
    bump_progress(run_id, done=12, total=70)

    body = _status(client, run_id).json()
    assert body["status"] == "processing"
    assert (body["done"], body["total"]) == (12, 70)
    assert body["docx_url"] is None
