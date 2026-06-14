"""Pricing config: credit packs, paper-cost matrix, tier→model resolution.

PACKAGES values come directly from Survify's PRICING_PACKAGES (USD prices,
credits per pack). PAPER_COST is a placeholder matrix; tune later.
"""
from __future__ import annotations

import os
from typing import TypedDict


class Package(TypedDict):
    id: str
    name: str
    price_cents: int
    old_price_cents: int
    credits: int


# Prices sized for a 60-70% gross margin over the gemini-2.5-flash API cost,
# given the charge rate of 1 credit = 1000 tokens. One auto-draft run ≈ 10,000
# credits (~10M tokens, ~$6-9 API cost), so the Starter pack covers exactly one
# run at ~$0.0025/credit (~66% margin at a 25% output mix). Larger packs apply a
# modest volume discount but stay ≥60% margin. Re-tune once token_ledger meters
# real tokens/run and the input:output split.
PACKAGES: list[Package] = [
    {
        "id": "starter_package",
        "name": "Starter package",
        "price_cents": 2499,       # $24.99 → $0.0025/credit, ~66% margin
        "old_price_cents": 3999,
        "credits": 10000,          # = one auto-draft run
    },
    {
        "id": "standard_package",
        "name": "Standard package",
        "price_cents": 5799,       # $57.99 → $0.00232/credit, ~63% margin
        "old_price_cents": 9999,
        "credits": 25000,          # ≈ 2.5 runs
    },
    {
        "id": "expert_package",
        "name": "Expert package",
        "price_cents": 12999,      # $129.99 → $0.00217/credit, ~61% margin
        "old_price_cents": 24999,
        "credits": 60000,          # ≈ 6 runs
    },
]

PACKAGES_BY_ID: dict[str, Package] = {p["id"]: p for p in PACKAGES}


PAPER_COST: dict[tuple[str, str], int] = {
    ("research", "standard"):  60, ("research", "premium"):  150,
    ("bachelor", "standard"): 120, ("bachelor", "premium"):  300,
    ("master",   "standard"): 240, ("master",   "premium"):  600,
    ("phd",      "standard"): 480, ("phd",      "premium"): 1200,
}


TIER_TO_MODEL: dict[str, str] = {
    "standard": "gemini-flash",
    "premium":  "gpt-5",
}

ALLOWED_TIERS: frozenset[str] = frozenset({"standard", "premium"})
ALLOWED_LEVELS: frozenset[str] = frozenset({"research", "bachelor", "master", "phd"})


def paper_cost(level: str, tier: str) -> int:
    if level not in ALLOWED_LEVELS:
        raise ValueError(f"unknown level: {level!r}")
    if tier not in ALLOWED_TIERS:
        raise ValueError(f"unknown tier: {tier!r}")
    return PAPER_COST[(level, tier)]


def resolve_model(tier: str) -> str:
    if tier not in ALLOWED_TIERS:
        raise ValueError(f"unknown tier: {tier!r}")
    env_key = f"DOTHESIS_{tier.upper()}_MODEL"
    return os.environ.get(env_key) or TIER_TO_MODEL[tier]
