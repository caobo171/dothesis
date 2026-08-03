import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Project, User


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


def _seed_projects(specs):
    """Create one owner plus a project per (name, focus, current_module) spec."""
    Session = get_session_factory()
    with Session() as s:
        owner = User(email="own@e.com", username="owner", password_hash="x", credit=0)
        s.add(owner)
        s.flush()
        for name, focus, current in specs:
            s.add(Project(user_id=owner.id, name=name, field="Marketing",
                          language="en", citation_style="apa",
                          focus=focus, current_module=current))
        s.commit()
        return owner


def test_admin_papers_lists_projects(admin):
    """Regression: this listed the legacy `papers` table, which has been empty
    since the v3 pivot, so the admin screen showed "0 total" while every real
    thesis sat in `projects`."""
    _seed_projects([(f"T{i}", None, "M1") for i in range(3)])

    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/papers", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 3
        item = data["items"][0]
        assert item["topic"].startswith("T")
        assert item["owner_email"] == "own@e.com"
        assert item["field"] == "Marketing"
        assert item["module"] == "M1"
        assert "status" in item
    finally:
        app.dependency_overrides.clear()


def test_admin_papers_module_filter_prefers_focus(admin):
    """focus wins over current_module, matching what the MODULE column shows."""
    _seed_projects([
        ("focused-on-m3", "M3", "M1"),   # focus set → M3
        ("no-focus-m1", None, "M1"),     # focus unset → falls back to M1
    ])

    client, app = _as(admin)
    try:
        m3 = client.post("/api/v1/admin/papers", json={"module": "M3"}).json()
        assert [i["topic"] for i in m3["items"]] == ["focused-on-m3"]

        m1 = client.post("/api/v1/admin/papers", json={"module": "M1"}).json()
        # The M3-focused project must NOT leak in via its current_module.
        assert [i["topic"] for i in m1["items"]] == ["no-focus-m1"]
    finally:
        app.dependency_overrides.clear()
