import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.db import get_session_factory
from app.models import CreditTransaction, Order, User


@pytest.fixture
def buyer():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="buyer@e.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


@pytest.fixture
def client_with_user(buyer):
    """Yields (client, user) with current_user dep overridden to return buyer."""
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: buyer
    yield TestClient(app), buyer
    app.dependency_overrides.pop(current_user, None)


def test_packages_returns_all_three():
    client = TestClient(create_app())
    r = client.post("/api/v1/credit/packages")
    assert r.status_code == 200
    data = r.json()
    ids = {p["id"] for p in data}
    assert ids == {"starter_package", "standard_package", "expert_package"}


def test_checkout_creates_order_and_returns_url(client_with_user):
    client, user = client_with_user
    with patch("app.routers.credit.create_checkout", return_value=("ck_test_123", "https://polar.test/checkout/abc")):
        r = client.post("/api/v1/credit/checkout", json={"package_id": "starter_package"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"] == "https://polar.test/checkout/abc"

    Session = get_session_factory()
    with Session() as s:
        orders = s.scalars(select(Order)).all()
        assert len(orders) == 1
        assert orders[0].polar_checkout_id == "ck_test_123"
        assert orders[0].credits == 300
        assert orders[0].amount_cents == 900
        assert orders[0].status == "pending"


def test_checkout_rejects_unknown_package(client_with_user):
    client, _ = client_with_user
    r = client.post("/api/v1/credit/checkout", json={"package_id": "nope"})
    assert r.status_code == 400


def test_polar_webhook_credits_user_idempotently(buyer, monkeypatch):
    monkeypatch.setenv("DOTHESIS_PAYMENTS", "dummy")
    Session = get_session_factory()
    with Session() as s:
        order = Order(
            user_id=buyer.id,
            package_id="standard_package",
            credits=700,
            amount_cents=1900,
            polar_checkout_id="ck_seeded",
            status="pending",
        )
        s.add(order)
        s.commit()
        order_id = order.id

    client = TestClient(create_app())
    payload = json.dumps({
        "type": "order.paid",
        "data": {"checkout_id": "ck_seeded", "id": "polar_order_abc"},
    }).encode()
    r = client.post(
        "/api/v1/credit/polar/webhook",
        content=payload,
        headers={"X-Polar-Signature": "any-in-dummy", "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text

    with Session() as s:
        u = s.get(User, buyer.id)
        assert u.credit == 700
        order = s.get(Order, order_id)
        assert order.status == "paid"
        ledger = s.scalars(select(CreditTransaction).where(CreditTransaction.user_id == u.id)).all()
        assert len(ledger) == 1
        assert ledger[0].delta == 700

    # Second delivery: no double-credit
    r2 = client.post(
        "/api/v1/credit/polar/webhook",
        content=payload,
        headers={"X-Polar-Signature": "any-in-dummy", "Content-Type": "application/json"},
    )
    assert r2.status_code == 200
    with Session() as s:
        u = s.get(User, buyer.id)
        assert u.credit == 700


def test_polar_webhook_missing_signature_is_400():
    client = TestClient(create_app())
    payload = b"{}"
    r = client.post("/api/v1/credit/polar/webhook", content=payload)
    assert r.status_code == 400
