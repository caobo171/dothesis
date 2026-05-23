import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Order, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_admin_orders_lists(admin):
    Session = get_session_factory()
    with Session() as s:
        buyer = User(email="b@e.com", password_hash="x", credit=0)
        s.add(buyer)
        s.flush()
        s.add(Order(
            user_id=buyer.id, package_id="standard_package",
            credits=700, amount_cents=1900, status="paid",
            polar_checkout_id="ck_xx",
        ))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.get("/api/v1/admin/orders")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["owner_email"] == "b@e.com"
        assert item["status"] == "paid"
    finally:
        app.dependency_overrides.clear()
