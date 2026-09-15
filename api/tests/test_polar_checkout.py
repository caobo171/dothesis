"""Polar checkout creation: one product, and OUR price on it.

Two bugs are pinned here, both of which reached production.

The first: `create_checkout` sent `product_id=order.package_id`, i.e. the string
`"starter_package"`, in a field the current API does not take. Verified against
the live API: 422 `{"loc": [..., "products"], "msg": "Field required"}`. Every
card payment was impossible, unnoticed only because production had no access
token and sat in dummy mode.

The second, and the reason this file was rewritten: the fix mapped each pack to
its own Polar product and sent **no amount**. That quietly handed Polar ownership
of the price. When `pricing.PACKAGES` was repriced on 2026-09-14 the page began
advertising $9 while Polar went on charging the $24.99 its product was created
with — a 2.8x overcharge that no test could have caught, because the number we
were asserting on was never the number being charged.

So the assertions below are about the AMOUNT as much as the product. Polar is
stubbed: it is a payment vendor, and a test that reached the real API would mint
live checkouts or need a sandbox token in CI. The stub records the request dict,
and what we send is exactly the part that was wrong both times.
"""
from __future__ import annotations

import sys
import uuid
from types import SimpleNamespace

import pytest

from app.models import Order
from app.polar_client import PolarError, create_checkout
from app.pricing import PACKAGES_BY_ID

PRODUCT_UUID = "71228e0e-675e-4523-9ce0-11a1a137c126"


def _order(package_id: str = "starter_package") -> Order:
    """An Order priced the way `credit.py` prices one — off `pricing.PACKAGES`."""
    pkg = PACKAGES_BY_ID[package_id]
    order = Order(
        user_id=uuid.uuid4(), package_id=package_id,
        credits=pkg["credits"], amount_cents=pkg["price_cents"], status="pending",
    )
    # Unsaved: the UUID default is applied on flush, and create_checkout puts the
    # id in checkout metadata, so give it one without touching a DB.
    order.id = uuid.uuid4()
    return order


@pytest.fixture
def sent(monkeypatch):
    """Stub `polar_sdk.Polar` and hand back the request dict we sent it.

    `create_checkout` imports polar_sdk inside the function body, so patching the
    module entry in sys.modules is what that import will resolve.
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


def _settings(**over):
    base = dict(
        dothesis_payments="polar",
        polar_access_token="polar_oat_test",
        polar_server="production",
        dothesis_base_url="https://app.dothesis.com",
        polar_product_id=PRODUCT_UUID,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def live_polar(monkeypatch):
    """Configured (non-dummy) Polar with the one product set."""
    monkeypatch.setattr("app.polar_client.get_settings", lambda: _settings())


def _price(sent: dict) -> dict:
    """The single price override out of the request."""
    return sent["prices"][PRODUCT_UUID][0]


# --- the amount ------------------------------------------------------------

@pytest.mark.parametrize("package_id", ["starter_package", "standard_package", "expert_package"])
def test_charges_the_price_in_pricing_packages(sent, live_polar, package_id):
    """THE regression. Every pack must bill the number `pricing.PACKAGES` holds.

    Derived from the table rather than pinned to 900/1900/4900: pinning the
    literal is what let the last reprice pass its tests while overcharging.
    """
    order = _order(package_id)
    create_checkout(order, return_url="https://r", cancel_url="https://c")
    assert _price(sent)["price_amount"] == PACKAGES_BY_ID[package_id]["price_cents"]


def test_the_amount_charged_equals_the_amount_recorded(sent, live_polar):
    """What Polar takes and what the Order says must be one number.

    They were two: the Order recorded `pricing.PACKAGES`, Polar billed whatever
    its product was created with, and nothing compared them. Reconciliation and
    every refund calculation read `amount_cents`.
    """
    order = _order("standard_package")
    create_checkout(order, return_url="https://r", cancel_url="https://c")
    assert _price(sent)["price_amount"] == order.amount_cents


def test_the_override_is_a_fixed_usd_price(sent, live_polar):
    """`amount_type` must be fixed — a custom/PWYW price would let the payer
    choose — and USD because `Order.amount_cents` is USD cents. A VND order goes
    through SePay and never reaches this function."""
    create_checkout(_order(), return_url="https://r", cancel_url="https://c")
    assert _price(sent) == {
        "amount_type": "fixed",
        "price_amount": 900,
        "price_currency": "usd",
    }


def test_the_price_override_is_keyed_by_the_product_it_overrides(sent, live_polar):
    """Polar keys `prices` by product id. Keyed by anything else the override is
    ignored and the product's own price is charged — silently, which is the whole
    failure mode this file exists for."""
    create_checkout(_order(), return_url="https://r", cancel_url="https://c")
    assert list(sent["prices"].keys()) == sent["products"]


# --- the product -----------------------------------------------------------

def test_sends_one_product_uuid_not_our_package_id(sent, live_polar):
    """"starter_package" is not a product UUID, and never was."""
    create_checkout(_order(), return_url="https://r", cancel_url="https://c")
    assert sent["products"] == [PRODUCT_UUID]
    assert "starter_package" not in str(sent["products"])


def test_every_pack_shares_the_one_product(sent, live_polar):
    """One product, three prices — not three products. A pack is distinguished by
    the amount we send, so adding a pack needs no vendor round trip."""
    seen = set()
    for package_id in ("starter_package", "standard_package", "expert_package"):
        create_checkout(_order(package_id), return_url="https://r", cancel_url="https://c")
        seen.add(tuple(sent["products"]))
    assert seen == {(PRODUCT_UUID,)}


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


# --- misconfiguration ------------------------------------------------------

def test_missing_product_id_raises_rather_than_calling_polar(sent, monkeypatch):
    """An unset POLAR_PRODUCT_ID is a broken deployment. Fail loudly here rather
    than send a malformed request and surface Polar's 422 as an opaque 502."""
    monkeypatch.setattr("app.polar_client.get_settings", lambda: _settings(polar_product_id=""))
    with pytest.raises(PolarError, match="POLAR_PRODUCT_ID"):
        create_checkout(_order(), return_url="https://r", cancel_url="https://c")
    assert sent == {}


def test_dummy_mode_still_short_circuits_before_any_product_lookup(monkeypatch):
    """Local dev has no product configured and must not need one."""
    monkeypatch.setattr(
        "app.polar_client.get_settings",
        lambda: _settings(dothesis_payments="dummy", polar_access_token="",
                          polar_server="sandbox", polar_product_id="",
                          dothesis_base_url="http://localhost:3000"),
    )
    order = _order()
    cid, url = create_checkout(order, return_url="https://r", cancel_url="https://c")
    assert cid.startswith("dummy_")
    assert str(order.id) in url
