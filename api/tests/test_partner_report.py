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
        "chapters": ["results"],
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
    # Avoid the LLM topic-inference + Crossref network calls in a unit test, and
    # bypass the M4 data-sufficiency gate (orthogonal to compose/presign here).
    monkeypatch.setattr(svc, "pdf_looks_like_analysis", lambda text: True)
    monkeypatch.setattr(svc, "_infer_topic", lambda text, lang: {})
    monkeypatch.setattr(svc, "_literature_search", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_compose_chapters",
                        lambda context_store, chapter_keys, language, **kw:
                        [{"title": "Chapter 4 — Results", "prose": "..."}])

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


# ---------------------------------------------------------------------------
# Task 4 — build_partner_context_store (optional M1/M2/M3, generate-if-missing).
# ---------------------------------------------------------------------------

def test_build_context_store_uses_provided_m1_verbatim(monkeypatch):
    called = {"infer": False}
    monkeypatch.setattr(svc, "_infer_topic", lambda *a, **k: called.__setitem__("infer", True) or {})
    monkeypatch.setattr(svc, "_budgeted_scout", lambda *a, **k: [])
    provided_m1 = {"research_title": "Given Title", "research_questions": ["RQ1"]}
    store = svc.build_partner_context_store(
        "AVE=0.6 HTMT ok R2=.4", notes=None, language="en", m1=provided_m1)
    assert store["m1_topic"]["research_title"] == "Given Title"
    assert called["infer"] is False  # provided -> NOT inferred


def test_build_context_store_generates_missing_m2(monkeypatch):
    monkeypatch.setattr(svc, "_infer_topic", lambda *a, **k: {"research_title": "Inferred"})
    monkeypatch.setattr(svc, "_infer_model", lambda *a, **k: {})
    scout_hits = [{"title": "Real Paper", "doi": "10.1/x"}]
    monkeypatch.setattr(svc, "_budgeted_scout", lambda *a, **k: scout_hits)
    store = svc.build_partner_context_store("AVE=0.6", notes=None, language="en")  # no m2
    assert store["m2_literature"]["literature_sources"] == scout_hits


# ---------------------------------------------------------------------------
# Task 5 — budgeted real M2 research with Crossref fallback.
# ---------------------------------------------------------------------------

def test_budgeted_scout_uses_real_scout_when_in_budget(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit
    monkeypatch.setattr(m2lit.scout_citations, "func",
                        lambda topic, min_n=8: [{"title": "Scouted", "doi": "10.1/a"}])
    out = svc._budgeted_scout("topic", ["RQ1"])
    assert out and out[0]["title"] == "Scouted"


def test_budgeted_scout_falls_back_on_timeout(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit

    def slow(topic, min_n=8):
        import time; time.sleep(5); return []
    monkeypatch.setattr(m2lit.scout_citations, "func", slow)
    monkeypatch.setattr(svc, "_M2_SCOUT_TIMEOUT_S", 0.2)  # force timeout fast
    monkeypatch.setattr(svc, "_literature_search",
                        lambda *a, **k: [{"title": "Crossref fallback"}])
    out = svc._budgeted_scout("topic", ["RQ1"])
    assert out == [{"title": "Crossref fallback"}]


def test_budgeted_scout_falls_back_on_error(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit

    def boom(topic, min_n=8):
        raise RuntimeError("scout down")
    monkeypatch.setattr(m2lit.scout_citations, "func", boom)
    monkeypatch.setattr(svc, "_literature_search", lambda *a, **k: [])
    assert svc._budgeted_scout("topic", []) == []
