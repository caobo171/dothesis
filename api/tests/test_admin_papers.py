import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Paper, User


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


def test_admin_papers_lists_all(admin):
    Session = get_session_factory()
    with Session() as s:
        owner = User(email="own@e.com", username="owner", password_hash="x", credit=0)
        s.add(owner)
        s.flush()
        for i in range(3):
            s.add(Paper(
                user_id=owner.id, topic=f"T{i}", academic_level="master",
                language="en", citation_style="apa", model="gemini-flash",
                model_tier="standard", sources_json={}, status="done",
            ))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/papers", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 3
        item = data["items"][0]
        assert "owner_email" in item
        assert "model_tier" in item
        assert "status" in item
    finally:
        app.dependency_overrides.clear()
