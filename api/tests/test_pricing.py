import pytest

from app.pricing import (
    PACKAGES,
    PAPER_COST,
    TIER_TO_MODEL,
    paper_cost,
    resolve_model,
)


def test_packages_match_configured_pricing():
    """Guard the live pack prices. These are no longer Survify's numbers.

    The packs were deliberately re-priced off the margin model documented in
    pricing.py; this test still asserted the original Survify figures
    (900¢/300 credits), so it failed on an intentional change. Repricing again
    is a business decision — update these numbers with it.
    """
    by_id = {p["id"]: p for p in PACKAGES}
    assert by_id["starter_package"]["price_cents"] == 2499
    assert by_id["starter_package"]["credits"] == 10000
    assert by_id["standard_package"]["price_cents"] == 5799
    assert by_id["standard_package"]["credits"] == 25000
    assert by_id["expert_package"]["price_cents"] == 12999
    assert by_id["expert_package"]["credits"] == 60000


def test_packages_are_discounted_and_scale_with_size():
    """The properties a repricing must never break, whatever the numbers become."""
    packs = [p for p in PACKAGES]
    for pkg in packs:
        assert pkg["credits"] > 0
        assert 0 < pkg["price_cents"] < pkg["old_price_cents"]
    by_size = sorted(packs, key=lambda p: p["credits"])
    # Bigger packs must never cost more per credit, or they're not worth buying.
    rates = [p["price_cents"] / p["credits"] for p in by_size]
    assert rates == sorted(rates, reverse=True)


def test_package_fields_present():
    for pkg in PACKAGES:
        assert {"id", "name", "price_cents", "old_price_cents", "credits"} <= set(pkg.keys())


def test_paper_cost_matrix_complete():
    expected_levels = {"research", "bachelor", "master", "phd"}
    expected_tiers = {"standard", "premium"}
    for level in expected_levels:
        for tier in expected_tiers:
            assert (level, tier) in PAPER_COST
            assert PAPER_COST[(level, tier)] > 0


def test_paper_cost_premium_is_more_expensive_than_standard():
    for level in {"research", "bachelor", "master", "phd"}:
        assert PAPER_COST[(level, "premium")] > PAPER_COST[(level, "standard")]


def test_paper_cost_phd_more_than_research():
    assert PAPER_COST[("phd", "standard")] > PAPER_COST[("research", "standard")]
    assert PAPER_COST[("phd", "premium")] > PAPER_COST[("research", "premium")]


def test_paper_cost_helper_returns_int():
    assert paper_cost("master", "standard") == PAPER_COST[("master", "standard")]
    assert isinstance(paper_cost("phd", "premium"), int)


def test_paper_cost_helper_raises_on_bad_input():
    with pytest.raises(ValueError):
        paper_cost("nonsense", "standard")
    with pytest.raises(ValueError):
        paper_cost("master", "deluxe")


def test_resolve_model_uses_tier_map():
    assert resolve_model("standard") == TIER_TO_MODEL["standard"]
    assert resolve_model("premium") == TIER_TO_MODEL["premium"]


def test_resolve_model_raises_on_bad_tier():
    with pytest.raises(ValueError):
        resolve_model("ultra")


def test_resolve_model_env_override(monkeypatch):
    monkeypatch.setenv("DOTHESIS_PREMIUM_MODEL", "gpt-5-custom")
    from app.pricing import resolve_model as r
    assert r("premium") == "gpt-5-custom"
