import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Order, User


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


def test_admin_orders_exposes_sepay_fields(admin):
    """A SePay order must carry its dong amount and its transfer memo.

    Without amount_vnd the admin can only see the USD list price (amount_cents
    is USD whatever the order was billed in), and without sepay_memo there is
    nothing to match against the bank statement when a transfer goes missing.
    """
    Session = get_session_factory()
    with Session() as s:
        buyer = User(email="vn@e.com", username="vnbuyer", password_hash="x", credit=0)
        s.add(buyer)
        s.flush()
        s.add(Order(
            user_id=buyer.id, package_id="starter_package",
            credits=10000, amount_cents=2499, currency="VND",
            provider="sepay", amount_vnd=657237, sepay_memo="DTABC123",
            external_txn_id="FT4242", status="paid",
        ))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/orders", json={})
        assert r.status_code == 200
        item = next(i for i in r.json()["items"] if i["owner_email"] == "vn@e.com")
        assert item["provider"] == "sepay"
        assert item["currency"] == "VND"
        assert item["amount_vnd"] == 657237
        assert item["sepay_memo"] == "DTABC123"
        assert item["external_txn_id"] == "FT4242"
    finally:
        app.dependency_overrides.clear()


def test_admin_orders_lists(admin):
    Session = get_session_factory()
    with Session() as s:
        buyer = User(email="b@e.com", username="buyer", password_hash="x", credit=0)
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
        r = client.post("/api/v1/admin/orders", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["owner_email"] == "b@e.com"
        assert item["status"] == "paid"
    finally:
        app.dependency_overrides.clear()
