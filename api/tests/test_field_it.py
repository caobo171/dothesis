"""Field-It route tests (F7 Tasks 3 & 4).

Auth/ownership/store seams are stubbed (roadmap.py pattern) so these pin the
handoff contract, the Google Form fallback, the M4 ingestion write, and the
ownership gate — not DB/provider wiring. No live provider, LLM, or DB query.
"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import field_it as fi


def _client(monkeypatch, handoff=None, authorize=lambda db, user, pid: None, auth=True):
    if handoff is not None:
        monkeypatch.setattr(fi, "_provider_create_survey", handoff)
    monkeypatch.setattr(fi, "_authorize", authorize)
    app = FastAPI()
    app.include_router(fi.router, prefix="/api/v1")
    if auth:
        app.dependency_overrides[fi.current_user] = lambda: object()
    app.dependency_overrides[fi.db_session] = lambda: None
    return TestClient(app)


# --- Task 3: handoff + fallback --------------------------------------------

def test_vi_defaults_to_fillform(monkeypatch):
    seen = {}

    def ok(provider, payload):
        seen["provider"] = provider
        return {"collection_id": "c1", "survey_url": "https://fillform.info/s/c1"}

    c = _client(monkeypatch, ok)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": []}, "sampling_plan": {"target_n": 200}, "language": "vi"})
    assert r.status_code == 200 and seen["provider"] == "fillform"
    assert r.json()["survey_url"].startswith("https://fillform.info")


def test_en_defaults_to_survify(monkeypatch):
    seen = {}

    def ok(provider, payload):
        seen["provider"] = provider
        return {"collection_id": "c2", "survey_url": "https://survify.net/s/c2"}

    c = _client(monkeypatch, ok)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": []}, "language": "en"})
    assert r.status_code == 200 and seen["provider"] == "survify"


def test_provider_failure_returns_google_fallback(monkeypatch):
    def boom(provider, payload):
        raise RuntimeError("provider down")

    c = _client(monkeypatch, boom)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": [{"text": "Q1"}]}, "sampling_plan": {}, "language": "en"})
    assert r.status_code == 200 and r.json()["fallback_google_script"]


def test_field_it_requires_auth(monkeypatch):
    # F0 #1: no token → 401, before any project write.
    c = _client(monkeypatch, auth=False)
    r = c.post("/api/v1/projects/abc/field-it", json={"instrument": {"items": []}})
    assert r.status_code == 401


def test_consent_notice_is_bilingual():
    # F0 #5: the folded consent/data-privacy generator. VI for the fillform
    # market, EN for survify; both cover voluntary + anonymous participation.
    from agent.tools.instrument import build_consent_notice
    vi = build_consent_notice("vi")
    en = build_consent_notice("en")
    assert "tự nguyện" in vi and "ẩn danh" in vi
    assert "voluntary" in en.lower() and "anonymous" in en.lower()


def test_fallback_form_carries_consent(monkeypatch):
    # The Google Form fallback must be ethics-complete: consent rides in the
    # form description.
    def boom(provider, payload):
        raise RuntimeError("down")

    c = _client(monkeypatch, boom)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": [{"text": "Q1"}]}, "language": "en"})
    assert "CONSENT" in r.json()["fallback_google_script"]


def test_field_it_rejects_non_owner(monkeypatch):
    def _deny(db, user, pid):
        raise HTTPException(403, detail={"error": {"code": "forbidden"}})

    c = _client(monkeypatch, lambda p, pl: {"collection_id": "x", "survey_url": "u"},
                authorize=_deny)
    r = c.post("/api/v1/projects/abc/field-it", json={"instrument": {"items": []}})
    assert r.status_code == 403
