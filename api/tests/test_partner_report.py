"""Partner report endpoint + service tests.

Covers the wiring, auth, and error mapping of the cross-product
("Powered by DoThesis") report path. The heavy engine pieces (pdfminer
extraction, LLM chapter composition, LibreOffice render, S3) are monkeypatched
— those are exercised by the M5 export tests, not here.

The router is mounted on a minimal FastAPI app so these tests don't need the
full create_app() stack (Postgres, orchestrator pool, AWS).
"""
from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import partner_report_service as svc
from app.partner_report_service import ReportError
from app.routers import partner_report as router_mod
from app.settings import get_settings

TOKEN = "test-partner-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    # settings is a cached singleton — force a fresh read of the env above.
    from app.settings import reset_settings
    reset_settings()

    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    return TestClient(app)


def _post(client, *, token=TOKEN, depth="analysis_report", body=b"%PDF-1.4 fake"):
    headers = {"X-Partner-Token": token} if token is not None else {}
    return client.post(
        "/api/v1/partner/report",
        headers=headers,
        files={"file": ("analysis.pdf", io.BytesIO(body), "application/pdf")},
        data={"depth": depth, "title": "My Study", "language": "en"},
    )


def test_missing_token_is_401(client):
    assert _post(client, token=None).status_code == 401


def test_wrong_token_is_401(client):
    assert _post(client, token="nope").status_code == 401


def test_happy_path_returns_urls_and_branding(client, monkeypatch):
    monkeypatch.setattr(svc, "generate_partner_report", lambda *a, **k: {
        "pages": 3,
        "depth": "analysis_report",
        "sections": ["Chapter 4 — Results"],
        "pdf_url": "https://s3/signed.pdf",
        "docx_url": "https://s3/signed.docx",
    })
    # Router imported the symbol by name — patch it there too.
    monkeypatch.setattr(router_mod, "generate_partner_report", svc.generate_partner_report)

    r = _post(client)
    assert r.status_code == 200
    body = r.json()
    assert body["powered_by"] == "DoThesis"
    assert body["pdf_url"] == "https://s3/signed.pdf"
    assert body["pages"] == 3


def test_no_extractable_text_is_422(client, monkeypatch):
    def boom(*a, **k):
        raise ReportError("no_extractable_text", "image-only scan")
    monkeypatch.setattr(router_mod, "generate_partner_report", boom)
    r = _post(client)
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "no_extractable_text"


def test_compose_failed_is_502(client, monkeypatch):
    def boom(*a, **k):
        raise ReportError("compose_failed", "engine returned nothing")
    monkeypatch.setattr(router_mod, "generate_partner_report", boom)
    assert _post(client).status_code == 502


def test_empty_file_is_422(client):
    assert _post(client, body=b"").status_code == 422


# ---------------------------------------------------------------------------
# Service layer — build context_store, compose subset, presign artifacts.
# ---------------------------------------------------------------------------

def test_service_bad_depth_raises():
    with pytest.raises(ReportError) as ei:
        svc.generate_partner_report(b"pdf", depth="nonsense")
    assert ei.value.code == "bad_depth"


def test_service_empty_text_raises(monkeypatch):
    monkeypatch.setattr(svc, "extract_pdf_text", lambda b: ("", 0))
    with pytest.raises(ReportError) as ei:
        svc.generate_partner_report(b"pdf", depth="analysis_report")
    assert ei.value.code == "no_extractable_text"


def test_service_composes_and_presigns(monkeypatch):
    monkeypatch.setattr(svc, "extract_pdf_text", lambda b: ("AVE=0.62, HTMT ok, R2=.41", 5))
    monkeypatch.setattr(svc, "_compose_analysis_sections",
                        lambda cs, lang: [{"title": "Chapter 4 — Results", "prose": "..."}])

    # Stub the lazily-imported run_export at its source module.
    import orchestrator.tools.m5_writing as m5
    monkeypatch.setattr(m5, "run_export", lambda sections, pid, references=None, language="en": [
        {"kind": "pdf", "s3_key": f"projects/{pid}/exports/report.pdf", "size_bytes": 10},
        {"kind": "docx", "s3_key": f"projects/{pid}/exports/report.docx", "size_bytes": 10},
    ])

    class _FakeS3:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f"https://s3.example/{Params['Key']}?sig=1"

    monkeypatch.setattr(svc, "_s3_from_env", lambda: _FakeS3())
    monkeypatch.setenv("S3_BUCKET", "bkt")

    out = svc.generate_partner_report(b"pdf", depth="analysis_report", title="T", language="en")
    assert out["pages"] == 5
    assert out["depth"] == "analysis_report"
    assert out["pdf_url"].endswith("report.pdf?sig=1")
    assert out["docx_url"].endswith("report.docx?sig=1")
    assert out["sections"] == ["Chapter 4 — Results"]
