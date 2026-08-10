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
from app.routers import partner_humanize as router_mod

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
    })
    r = _scan(client)
    assert r.status_code == 200
    assert r.json()["chars"] == 86_400
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
