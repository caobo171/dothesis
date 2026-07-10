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


# --- Task 4: results ingestion ---------------------------------------------

def test_results_ingest_writes_m4(monkeypatch):
    written = {}
    monkeypatch.setattr(fi, "_store_for", lambda pid: type("S", (), {
        "set_field_it_results": lambda self, data: written.update(data)})())
    c = _client(monkeypatch)
    r = c.post("/api/v1/projects/abc/field-it/results",
               json={"collection_id": "c1", "responses": [{"q1": 5}],
                     "quality": [{"straight_lined": False, "duration_s": 220}]})
    assert r.status_code == 200 and written["collection_id"] == "c1"


def test_results_bad_payload_is_4xx(monkeypatch):
    # Missing collection_id / responses → pydantic 422 (auth passes first).
    c = _client(monkeypatch)
    assert c.post("/api/v1/projects/abc/field-it/results", json={"nope": 1}).status_code == 422


def test_results_ingest_rejects_non_owner(monkeypatch):
    def _deny(db, user, pid):
        raise HTTPException(403, detail={"error": {"code": "forbidden"}})

    c = _client(monkeypatch, authorize=_deny)
    r = c.post("/api/v1/projects/abc/field-it/results",
               json={"collection_id": "c1", "responses": [{"q1": 5}]})
    assert r.status_code == 403


def test_set_field_it_results_round_trips_and_is_m4_owned(tmp_path):
    # The store method persists into the flat contextStore, and the three keys
    # are M4-owned so DbProjectStateStore._save carries them into m4_analysis
    # (closing the prod persistence gap). Ingesting data must NOT move status.
    from agent.state import SLICE_OWNERSHIP, ProjectStateStore
    store = ProjectStateStore(tmp_path)
    store.set_field_it_results({"collection_id": "c1", "responses": [{"q1": 5}],
                                "quality": [{"straight_lined": False}]})
    cs = store.load()["contextStore"]
    assert cs["field_it_collection_id"] == "c1"
    assert cs["field_it_responses"] == [{"q1": 5}]
    assert cs["field_it_quality"] == [{"straight_lined": False}]
    for k in ("field_it_collection_id", "field_it_responses", "field_it_quality"):
        assert k in SLICE_OWNERSHIP["M4"]
    assert store.load()["status"]["M4"] == "locked"
