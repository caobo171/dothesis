import pytest

from app.pricing import (
    PACKAGES,
    PAPER_COST,
    TIER_TO_MODEL,
    paper_cost,
    resolve_model,
)


def test_packages_match_survify_pricing():
    by_id = {p["id"]: p for p in PACKAGES}
    assert by_id["starter_package"]["price_cents"] == 900
    assert by_id["starter_package"]["credits"] == 300
    assert by_id["standard_package"]["price_cents"] == 1900
    assert by_id["standard_package"]["credits"] == 700
    assert by_id["expert_package"]["price_cents"] == 4900
    assert by_id["expert_package"]["credits"] == 2000


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
    monkeypatch.setenv("OPENDRAFT_PREMIUM_MODEL", "gpt-5-custom")
    from app.pricing import resolve_model as r
    assert r("premium") == "gpt-5-custom"
