"""Polar checkout creation: our package id -> Polar's product UUID.

The two are not the same thing and never were. `pricing.PACKAGES` keys on
`"starter_package"`; Polar keys on a product UUID it minted. `create_checkout`
used to send `product_id=order.package_id`, which is both the wrong field name
(the API takes a `products` ARRAY) and the wrong value. Verified against the
live API before this was fixed: 422 `{"loc": [..., "products"], "msg": "Field
required"}` — i.e. every real card payment was impossible, and the only reason
nobody noticed is that production had no access token and so sat in dummy mode.

Polar itself is stubbed here. It is a payment vendor: a test that reached the
real API would either mint live checkouts or need a sandbox token in CI. The
stub records the request dict, and the assertions are about what WE send —
which is exactly the part that was wrong.
"""
from __future__ import annotations

import sys
import uuid
from types import SimpleNamespace

import pytest

from app.models import Order
from app.polar_client import PolarError, create_checkout

STARTER_UUID = "802d4204-8c47-4d10-af1c-81d362c43239"
EXPERT_UUID = "0020bb12-c950-449f-9392-2363782e1774"


def _order(package_id: str = "starter_package") -> Order:
    order = Order(
        user_id=uuid.uuid4(), package_id=package_id,
        credits=10000, amount_cents=2499, status="pending",
    )
    # Unsaved: the UUID default is applied on flush, and create_checkout puts
    # the id in checkout metadata, so give it one without touching a DB.
    order.id = uuid.uuid4()
    return order


@pytest.fixture
def sent(monkeypatch):
    """Stub `polar_sdk.Polar` and hand back the request dict we sent it.

    `create_checkout` imports polar_sdk inside the function body, so patching
    the module entry in sys.modules is what that import will resolve.
    """
    captured: dict = {}

    class _Checkouts:
        def create(self, request):
            captured.update(request)
            return SimpleNamespace(id="polar_checkout_abc", url="https://polar.sh/checkout/abc")

    class _Polar:
        def __init__(self, access_token, server):
            self.checkouts = _Checkouts()

    monkeypatch.setitem(sys.modules, "polar_sdk", SimpleNamespace(Polar=_Polar))
    return captured


@pytest.fixture
def live_polar(monkeypatch):
    """Configured (non-dummy) Polar with the three packs mapped."""
    monkeypatch.setattr(
        "app.polar_client.get_settings",
        lambda: SimpleNamespace(
            dothesis_payments="polar",
            polar_access_token="polar_oat_test",
            polar_server="production",
            dothesis_base_url="https://app.dothesis.com",
            polar_product_ids=(
                f"starter_package={STARTER_UUID},expert_package={EXPERT_UUID}"
            ),
        ),
    )


def test_sends_the_polar_product_uuid_not_our_package_id(sent, live_polar):
    """The bug, stated directly: "starter_package" is not a product UUID."""
    create_checkout(_order(), return_url="https://app.dothesis.com/credit?polar=success",
                    cancel_url="https://app.dothesis.com/credit?polar=cancel")
    assert sent["products"] == [STARTER_UUID]
    assert "starter_package" not in str(sent["products"])


def test_sends_products_as_a_list_not_a_product_id_field(sent, live_polar):
    """The current API takes `products: [...]`; `product_id` is silently dropped
    and the request 422s on the missing required field."""
    create_checkout(_order(), return_url="https://r", cancel_url="https://c")
    assert "product_id" not in sent
    assert isinstance(sent["products"], list)


def test_carries_order_and_user_ids_in_metadata(sent, live_polar):
    """The webhook matches on checkout_id, but metadata is what makes a payment
    traceable back to a user when support has to reconcile one by hand."""
    order = _order()
    create_checkout(order, return_url="https://r", cancel_url="https://c")
    assert sent["metadata"] == {"order_id": str(order.id), "user_id": str(order.user_id)}


def test_unmapped_package_raises_rather_than_calling_polar(sent, live_polar):
    """A pack present in pricing.PACKAGES but absent from POLAR_PRODUCT_IDS is an
    operator error. It must fail loudly here — not send a malformed request and
    surface as an opaque 502 after a round trip."""
    with pytest.raises(PolarError, match="standard_package"):
        create_checkout(_order("standard_package"), return_url="https://r", cancel_url="https://c")
    assert sent == {}


def test_dummy_mode_still_short_circuits_before_any_product_lookup(monkeypatch):
    """Local dev has no product mapping and must not need one."""
    monkeypatch.setattr(
        "app.polar_client.get_settings",
        lambda: SimpleNamespace(
            dothesis_payments="dummy", polar_access_token="", polar_server="sandbox",
            dothesis_base_url="http://localhost:3000", polar_product_ids="",
        ),
    )
    order = _order()
    cid, url = create_checkout(order, return_url="https://r", cancel_url="https://c")
    assert cid.startswith("dummy_")
    assert str(order.id) in url
