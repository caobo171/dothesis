import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Job, Paper, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", username="admin", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_admin_jobs_lists_recent(admin):
    Session = get_session_factory()
    with Session() as s:
        owner = User(email="o@e.com", username="owner", password_hash="x", credit=0)
        s.add(owner)
        s.flush()
        paper = Paper(
            user_id=owner.id, topic="X", academic_level="research",
            language="en", citation_style="apa", model="gemini-flash",
            model_tier="standard", sources_json={}, status="running",
        )
        s.add(paper)
        s.flush()
        s.add(Job(paper_id=paper.id, status="running"))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/jobs", json={"status": "running"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["status"] == "running"
        assert "paper_topic" in item
        assert "owner_email" in item
    finally:
        app.dependency_overrides.clear()
