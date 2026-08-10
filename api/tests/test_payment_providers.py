"""PayPal + SePay checkout/webhook flows (dummy mode — no real provider calls)."""
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, Order, User


@pytest.fixture(autouse=True)
def _dummy_payments(monkeypatch):
    # Dummy mode: providers skip real API calls; webhooks skip signature/apikey.
    monkeypatch.setenv("DOTHESIS_PAYMENTS", "dummy")
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_BANK_CODE", "OCB")
    monkeypatch.setenv("SEPAY_MEMO_PREFIX", "DTS")
    monkeypatch.setenv("USD_TO_VND", "25000")
    monkeypatch.setenv("SEPAY_API_KEY", "test-key")
    from app.settings import reset_settings
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def buyer():
    Session = get_session_factory()
    with Session() as s:
        u = User(email=f"b{uuid.uuid4().hex[:8]}@e.com",
                 username=f"b{uuid.uuid4().hex[:8]}", password_hash="x", credit=0)
        s.add(u); s.commit()
        return u


@pytest.fixture
def client_with_user(buyer):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: buyer
    yield TestClient(app), buyer
    app.dependency_overrides.pop(current_user, None)


def _webhook_url() -> str:
    """Resolve the SePay webhook URL the same way the app mounts it.

    Never hardcode the path here: it is env-configurable so it can be rotated,
    and a literal would make these tests pass against a stale route.
    """
    from app.routers.credit import sepay_webhook_path
    return f"/api/v1{sepay_webhook_path()}"


def _grab_order(provider: str) -> Order:
    Session = get_session_factory()
    with Session() as s:
        return s.scalars(select(Order).where(Order.provider == provider)).one()


def test_methods_lists_all_in_dummy():
    r = TestClient(create_app()).post("/api/v1/credit/methods")
    assert r.status_code == 200
    body = r.json()
    assert set(body["methods"]) >= {"polar", "paypal", "sepay"}
    assert body["sepay_enabled"] is True


# --- PayPal ----------------------------------------------------------------

def test_paypal_create_then_capture_grants_once(client_with_user):
    client, buyer = client_with_user
    r = client.post("/api/v1/credit/paypal/create-order", json={"package_id": "starter_package"})
    assert r.status_code == 200, r.text
    ppid = r.json()["paypal_order_id"]
    assert r.json()["approval_url"]

    order = _grab_order("paypal")
    assert order.status == "pending" and order.credits == 10000

    cap = client.post("/api/v1/credit/paypal/capture", json={"paypal_order_id": ppid})
    assert cap.status_code == 200, cap.text

    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 10000
        assert s.get(Order, order.id).status == "paid"
        assert len(s.scalars(select(CreditTransaction).where(
            CreditTransaction.user_id == buyer.id)).all()) == 1

    # Re-capture is a no-op (idempotent).
    cap2 = client.post("/api/v1/credit/paypal/capture", json={"paypal_order_id": ppid})
    assert cap2.json().get("already_paid") is True
    with Session() as s:
        assert s.get(User, buyer.id).credit == 10000


def test_paypal_webhook_grants_via_custom_id(client_with_user):
    client, buyer = client_with_user
    client.post("/api/v1/credit/paypal/create-order", json={"package_id": "standard_package"})
    order = _grab_order("paypal")
    payload = json.dumps({
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "cap_xyz", "custom_id": str(order.id)},
    }).encode()
    r = client.post("/api/v1/credit/paypal/webhook", content=payload,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 25000
        assert s.get(Order, order.id).status == "paid"


# --- SePay -----------------------------------------------------------------

def test_packages_price_vnd_matches_sepay_intent(client_with_user):
    """The dong price on the pricing card must equal the dong in the QR.

    They are two endpoints, so nothing but this test stops one from being
    converted differently (or client-side) and quoting a VN student an amount
    the transfer then contradicts.
    """
    client, _ = client_with_user
    pkgs = client.post("/api/v1/credit/packages").json()
    starter = next(p for p in pkgs if p["id"] == "starter_package")
    assert starter["price_vnd"] == round(2499 / 100 * 25000)  # $24.99 → 624,750₫
    assert starter["old_price_vnd"] == round(3999 / 100 * 25000)

    intent = client.post("/api/v1/credit/sepay/intent",
                         json={"package_id": "starter_package"}).json()
    assert intent["amount_vnd"] == starter["price_vnd"]


def test_sepay_intent_returns_qr_and_vnd(client_with_user):
    client, _ = client_with_user
    r = client.post("/api/v1/credit/sepay/intent", json={"package_id": "starter_package"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount_vnd"] == round(2499 / 100 * 25000)  # $24.99 → 624,750₫
    # Short + numeric (DTS1234), because a human retypes this into a bank app.
    assert re.fullmatch(r"DTS\d{4,}", body["memo"]), body["memo"]
    assert "qr.sepay.vn/img" in body["qr_url"]
    assert body["memo"] in body["qr_url"]
    # OCB is a per-merchant virtual account: no routing prefix to prepend.
    assert body["transfer_content"] == body["memo"]


def test_sepay_codes_are_unique_per_order(client_with_user):
    """Two intents must never share a code — one transfer, one order."""
    client, _ = client_with_user
    codes = {
        client.post("/api/v1/credit/sepay/intent",
                    json={"package_id": "starter_package"}).json()["memo"]
        for _ in range(3)
    }
    assert len(codes) == 3, codes


def test_sepay_vietinbank_prepends_routing_prefix(client_with_user, monkeypatch):
    """VietinBank is SePay's shared account — without "SEVQR TKP " the transfer
    is never routed to us, so it has to be in both the QR and the shown content.
    """
    monkeypatch.setenv("SEPAY_BANK_CODE", "VietinBank")
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "107868958175")
    from app.settings import reset_settings
    reset_settings()
    client, _ = client_with_user
    body = client.post("/api/v1/credit/sepay/intent",
                       json={"package_id": "starter_package"}).json()
    assert body["transfer_content"] == f"SEVQR TKP {body['memo']}"
    assert "SEVQR" in body["qr_url"]


def test_sepay_webhook_ignores_another_brands_code(client_with_user):
    """The bank account is shared with Fillform (FFV codes). Their transfers
    must fall through untouched rather than land on some DoThesis order.
    """
    client, buyer = client_with_user
    client.post("/api/v1/credit/sepay/intent", json={"package_id": "starter_package"})
    payload = json.dumps({
        "transferType": "in", "transferAmount": 999_000,
        "referenceCode": "FT_OTHER_BRAND", "content": "SEVQR TKP FFV1234",
    }).encode()
    r = client.post(_webhook_url(), content=payload,
                    headers={"Authorization": "Apikey test-key",
                             "Content-Type": "application/json"})
    assert r.json().get("ignored") == "no_memo"
    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 0


def test_sepay_webhook_matches_memo_trailed_by_digits(client_with_user):
    """Banks echo the content undelimited: "DTS1234 20260810" collapses to
    "DTS123420260810". The longest-first read must still find the order.
    """
    client, buyer = client_with_user
    intent = client.post("/api/v1/credit/sepay/intent",
                         json={"package_id": "starter_package"}).json()
    payload = json.dumps({
        "transferType": "in", "transferAmount": intent["amount_vnd"],
        "referenceCode": "FT_TRAILING",
        "content": f"SEVQR TKP {intent['memo']} 20260810",
    }).encode()
    r = client.post(_webhook_url(), content=payload,
                    headers={"Authorization": "Apikey test-key",
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 10000


def test_sepay_webhook_matches_memo_and_grants_once(client_with_user):
    client, buyer = client_with_user
    intent = client.post("/api/v1/credit/sepay/intent",
                         json={"package_id": "starter_package"}).json()
    memo, amount_vnd = intent["memo"], intent["amount_vnd"]

    # SePay wraps the memo in extra text; matcher must still find it.
    payload = json.dumps({
        "transferType": "in",
        "transferAmount": amount_vnd,
        "referenceCode": "FT123456",
        "content": f"NHANTIEN {memo} GD",
    }).encode()
    r = client.post(_webhook_url(), content=payload,
                    headers={"Authorization": "Apikey test-key",
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text

    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 10000

    # Duplicate delivery (same referenceCode) → no double-credit.
    r2 = client.post(_webhook_url(), content=payload,
                     headers={"Authorization": "Apikey test-key",
                              "Content-Type": "application/json"})
    assert r2.status_code == 200
    with Session() as s:
        assert s.get(User, buyer.id).credit == 10000


def test_sepay_webhook_path_is_obscure_and_configurable(monkeypatch):
    """The webhook must not sit at a guessable path, and must follow the env.

    Rotating SEPAY_WEBHOOK_PATH has to actually move the route — if it were
    bound at import time the old path would keep answering after a rotation.
    """
    from app.settings import reset_settings

    # The predictable path a scanner would try is gone.
    assert TestClient(create_app()).post(
        "/api/v1/credit/sepay/webhook", json={}).status_code == 404

    monkeypatch.setenv("SEPAY_WEBHOOK_PATH", "rotated/9999/xyz")
    monkeypatch.setenv("SEPAY_API_KEY", "test-key")
    monkeypatch.setenv("DOTHESIS_PAYMENTS", "polar")  # enforce the apikey check
    reset_settings()
    client = TestClient(create_app())

    # 401 (not 404) proves the route moved and is reachable at the new path.
    assert client.post("/api/v1/rotated/9999/xyz", json={},
                       headers={"Authorization": "Apikey wrong"}).status_code == 401
    assert client.post("/api/v1/h00k/71204/cr3d1t", json={}).status_code == 404


def test_sepay_webhook_stays_out_of_openapi():
    """The path must not be published in /docs — that would undo the obscurity."""
    paths = create_app().openapi()["paths"]
    assert not [p for p in paths if "cr3d1t" in p or "sepay/webhook" in p]


def test_sepay_webhook_rejects_bad_apikey(client_with_user, monkeypatch):
    # Leave dummy mode so the apikey check is enforced.
    monkeypatch.setenv("DOTHESIS_PAYMENTS", "polar")
    from app.settings import reset_settings
    reset_settings()
    client = TestClient(create_app())
    r = client.post(_webhook_url(),
                    content=b'{"transferType":"in"}',
                    headers={"Authorization": "Apikey wrong",
                             "Content-Type": "application/json"})
    assert r.status_code == 401


def test_sepay_webhook_ignores_underpayment(client_with_user):
    client, buyer = client_with_user
    intent = client.post("/api/v1/credit/sepay/intent",
                         json={"package_id": "starter_package"}).json()
    payload = json.dumps({
        "transferType": "in",
        "transferAmount": 1000,  # far below the VND price
        "referenceCode": "FT999",
        "content": intent["memo"],
    }).encode()
    r = client.post(_webhook_url(), content=payload,
                    headers={"Authorization": "Apikey test-key",
                             "Content-Type": "application/json"})
    assert r.json().get("ignored") == "underpaid"
    Session = get_session_factory()
    with Session() as s:
        assert s.get(User, buyer.id).credit == 0
