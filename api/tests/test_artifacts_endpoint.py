"""Tests for the artifact readiness + import endpoints (Phase 2)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, User

_FULL_TOPIC = {
    "research_title": "X", "field": "Marketing", "research_type": "quantitative",
    "target_population": "Gen Z", "scope": "National",
    "objectives": ["o1"], "research_questions": ["q1"],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _auth_and_project(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        from app.security import create_session
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return uuid.UUID(pid)


def _seed_slice(pid, **slices):
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, pid)
        for k, v in slices.items():
            setattr(cs, k, v)
        db.add(cs); db.commit()


def test_artifacts_endpoint_empty_project_topic_ready(client):
    pid = _auth_and_project(client)
    # GET→POST migration: read-only route now POST (same path).
    r = client.post(f"/api/v1/projects/{pid}/artifacts")
    assert r.status_code == 200
    body = r.json()
    assert body["topic"] == "ready"
    assert body["literature"] == "blocked"


def test_artifacts_endpoint_reflects_seeded_topic(client):
    pid = _auth_and_project(client)
    _seed_slice(pid, m1_topic=_FULL_TOPIC)
    body = client.post(f"/api/v1/projects/{pid}/artifacts").json()
    assert body["topic"] == "done"
    assert body["literature"] == "ready"


def test_import_seeds_context_and_returns_readiness(client):
    pid = _auth_and_project(client)
    r = client.post(f"/api/v1/projects/{pid}/import",
                    json={"slices": {"m1_topic": _FULL_TOPIC}})
    assert r.status_code == 200
    body = r.json()
    assert body["topic"] == "done"
    assert body["literature"] == "ready"
    # And it persisted — a fresh readiness read reflects it.
    body2 = client.post(f"/api/v1/projects/{pid}/artifacts").json()
    assert body2["topic"] == "done"


def test_import_tags_source_imported(client):
    pid = _auth_and_project(client)
    client.post(f"/api/v1/projects/{pid}/import",
                json={"slices": {"m1_topic": _FULL_TOPIC}})
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, pid)
        assert cs.m1_topic["_source"] == "imported"


def test_assess_endpoint_returns_detection_and_preview(client, monkeypatch):
    pid = _auth_and_project(client)
    monkeypatch.setattr("orchestrator.intake.assess_work",
                        lambda text, llm=None: {"m1_topic": _FULL_TOPIC})
    r = client.post(f"/api/v1/projects/{pid}/assess",
                    json={"text": "Here is my thesis draft so far ..."})
    assert r.status_code == 200
    body = r.json()
    assert body["detected"]["m1_topic"]["research_title"] == "X"
    assert body["readiness_if_applied"]["topic"] == "done"
    # Dry-run: nothing is committed until the client calls /import.
    after = client.post(f"/api/v1/projects/{pid}/artifacts").json()
    assert after["topic"] == "ready"


def test_reconstruct_endpoint_proposes_candidate_with_structural_gate(client, monkeypatch):
    pid = _auth_and_project(client)
    _seed_slice(pid,
                m1_topic={"research_title": "X", "research_type": "quantitative"},
                m4_analysis={"data_type_detected": "SmartPLS", "results": {"p": {}}})
    monkeypatch.setattr(
        "orchestrator.backfill.reconstruct_artifact",
        lambda key, cs, llm=None: {
            "paradigm": "quantitative", "design": "PLS-SEM", "tool": "SmartPLS",
            "sampling_strategy": "convenience", "target_sample_size": 237,
            "_source": "reconstructed",
        },
    )
    r = client.post(f"/api/v1/projects/{pid}/reconstruct/design")
    assert r.status_code == 200
    body = r.json()
    assert body["candidate"]["design"] == "PLS-SEM"
    assert body["ready_to_confirm"] is True   # structural gate passes the skeleton
    # Dry-run: not committed.
    after = client.post(f"/api/v1/projects/{pid}/artifacts").json()
    assert after["design"] != "done"


def test_reconstruct_endpoint_rejects_unknown_artifact(client):
    pid = _auth_and_project(client)
    r = client.post(f"/api/v1/projects/{pid}/reconstruct/bogus")
    assert r.status_code == 422


def test_impact_endpoint_lists_dependents_and_stale(client):
    """I2: GET /projects/{id}/impact/{artifact} surfaces the blast radius of
    editing an upstream slice — which DONE downstream artifacts may need
    revisiting, plus the full transitive dependents set so the frontend can
    grey-out / flag them. Powers the 'editing this step invalidates these
    later steps' UX promised in I1."""
    pid = _auth_and_project(client)
    # Seed topic AND literature so 'literature' is done and 'topic' edit
    # would mark it stale.
    _seed_slice(pid, m1_topic=_FULL_TOPIC,
                m2_literature={"research_state_summary": "X",
                               "research_gaps": [{"id": "1"}],
                               "literature_review_doc": "doc",
                               "_source": "imported",
                               "confirmed_at": "2026-05-31"})
    # GET→POST migration: read-only impact route now POST (same path).
    r = client.post(f"/api/v1/projects/{pid}/impact/topic")
    assert r.status_code == 200
    body = r.json()
    # Dependents closure of topic includes literature + everything downstream.
    assert "literature" in body["dependents"]
    # Only DONE dependents appear in `stale` — literature is done, others not.
    assert "literature" in body["stale"]
    assert "analysis" not in body["stale"]  # not done


def test_impact_endpoint_empty_stale_when_nothing_done_downstream(client):
    """When the upstream is editable but nothing downstream is done yet,
    `stale` is empty — there's nothing committed to invalidate. `dependents`
    still lists the full closure so the UI can show the potential impact."""
    pid = _auth_and_project(client)
    _seed_slice(pid, m1_topic=_FULL_TOPIC)
    body = client.post(f"/api/v1/projects/{pid}/impact/topic").json()
    assert body["stale"] == []
    assert "literature" in body["dependents"]  # closure still populated


def test_impact_endpoint_rejects_unknown_artifact(client):
    pid = _auth_and_project(client)
    r = client.post(f"/api/v1/projects/{pid}/impact/bogus")
    assert r.status_code == 422


def test_impact_endpoint_requires_project_ownership(client):
    """Same auth gate as /artifacts — a user can't peek at another user's
    project's impact map. Use a fresh non-existent project id to trigger
    the 404 path (we don't have a 2nd-user fixture here, but the underlying
    _owned_project helper conflates both 'not owned' and 'not found' to
    avoid leaking project existence)."""
    _auth_and_project(client)
    other = uuid.uuid4()
    r = client.post(f"/api/v1/projects/{other}/impact/topic")
    assert r.status_code == 404
