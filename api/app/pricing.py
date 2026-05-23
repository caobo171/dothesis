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


PACKAGES: list[Package] = [
    {
        "id": "starter_package",
        "name": "Starter package",
        "price_cents": 900,
        "old_price_cents": 1500,
        "credits": 300,
    },
    {
        "id": "standard_package",
        "name": "Standard package",
        "price_cents": 1900,
        "old_price_cents": 3500,
        "credits": 700,
    },
    {
        "id": "expert_package",
        "name": "Expert package",
        "price_cents": 4900,
        "old_price_cents": 10000,
        "credits": 2000,
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
    env_key = f"OPENDRAFT_{tier.upper()}_MODEL"
    return os.environ.get(env_key) or TIER_TO_MODEL[tier]
