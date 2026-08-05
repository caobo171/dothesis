"""Pricing config: credit packs, paper-cost matrix, tier→model resolution.

PACKAGES values come directly from Survify's PRICING_PACKAGES (USD prices,
credits per pack). PAPER_COST is a placeholder matrix; tune later.
"""
from __future__ import annotations

import logging
import os
from typing import TypedDict

# api -> quality is an established layering direction: quality is its own
# distribution (dothesis-quality, see quality/pyproject.toml, whose own comment
# states it exists to be importable "from the api process"), agent/tools/writing.py
# already imports quality.rubric, and api/tests import quality.model_prices. It is
# NOT the banned direction — that is agent -> api.app, which this does not touch.
from quality.model_prices import MODEL_PRICES


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
#
# ⚠️ STALE since the gemini-3.5-flash switch (2026-06-30), and MORE stale now.
# The multiplier no longer guesses 4.0 from the model's name — it reads
# quality/model_prices.py, where 3.5-flash is $1.50/$9.00 (July-2026 research,
# corroborated by the live Ofox gateway pull), not the $0.50/$3.00 in the stale
# engine/utils/model_config.py the old guess was based on. The honest rate is
# ~12.9x, so a 10M-token run debits ~129,000 credits, not the ~40,000 this comment
# assumed and nowhere near the 10,000 the packs were sized for: the Starter pack
# now covers ~1/13 of a run. 4.0 was under-billing the production default ~3.2x.
# The dollar prices/credits below are unchanged (still a business decision), but
# the gap is now 13x, not 4x. Decide before the next pricing page ships: raise pack
# credits, raise pack prices, move to a cheaper default model, or accept the margin.
# Full evidence: .superpowers/sdd/fix-credit-multiplier-report.md
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


# --- standalone tools -------------------------------------------------------
#
# Tools that call a model are billed on TOKENS (credit_multiplier, below) — the
# cost is real and varies with the document, so a flat fee would be wrong in
# both directions.
#
# Tools that call NO model still cost something: a CrossRef round trip, a
# vendor's similarity check, CPU. They were charging nothing at all, which is
# not a decision anyone made — it fell out of billing being wired to token usage
# and those tools having none. These are the flat rates.
#
# THE UNIT IS A LOOKUP. One CrossRef query = 1 credit (~$0.0025 at Starter pack
# rates), so checking a 40-entry reference list costs 40 credits (~$0.10) and
# checking one reference costs 1. That keeps the price proportional to the work
# without needing a second pricing concept, and it is explainable to a student:
# you pay per source we go and check.
#
# ⚠️ These are a first pass, chosen for shape not for margin. Nobody has costed a
# CrossRef call against a support ticket. Change the numbers here — every route
# reads this table, nothing hardcodes a price.
TOOL_COST_PER_UNIT: dict[str, int] = {
    # per CrossRef lookup
    "verify-citation":  1,
    "verify-citations": 1,
    # per distinct source resolved out of the document (phase A). Phase B's
    # model calls are billed on tokens on top of this.
    "cite-docx":        1,
}

TOOL_COST_FLAT: dict[str, int] = {
    # Local stylometry, no network, no model. Priced as a token gesture rather
    # than free, so the run appears in the ledger like every other one.
    "writing-rhythm":   1,
    # A vendor similarity check is the one tool with a real per-call invoice
    # attached. Charged only on a successful check — an unconfigured deployment
    # returns provider_not_configured and must not bill for a check it did not
    # perform.
    "plagiarism-check": 5,
}

# Charged at zero, deliberately, and listed so it is a decision rather than an
# omission:
#
#   extract-text          the INPUT step for the paid tools. Billing it means a
#                         student pays twice for the same file — once to read
#                         it, once to humanize it.
#   document/scan         the confirm-before-you-spend step. Both exist so a
#   document/cite/scan    student can see the size of the job BEFORE agreeing to
#                         pay for it; charging for the estimate defeats the
#                         entire point of showing it.
TOOL_FREE: frozenset[str] = frozenset({
    "extract-text", "scan-docx", "scan-cite-docx",
})


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


# The definitional baseline: the credit rate (1 credit ≈ 1000 tokens) is calibrated
# on this model, so its multiplier is 1.0 BY CONSTRUCTION, not by a stored constant.
BASELINE_MODEL = "gemini-2.5-flash"

# How the input/output prices are weighted into ONE "blended" price.
#
# Made explicit because the old comment reasoned "~4x blended on input-heavy thesis
# turns" without ever saying what "blended" meant — so the numbers could not be
# checked or re-derived. DoThesis turns are input-heavy: the agent re-sends the
# thesis context, skills, and slice state every turn and emits comparatively little
# prose. 25% is not a new guess — it is the SAME output mix the pack margins above
# are already sized on ("~66% margin at a 25% output mix"), so billing and pack
# pricing now reason about the token mix identically instead of disagreeing.
#
# Sanity check against the number this replaces: 3.x-flash at the old table's
# $0.50/$3.00 blends to 4.3x here, versus the 4.0 the old comment asserted — close
# enough to confirm 25% is the weighting that was meant all along.
#
# Re-tune from token_ledger once it reports the real input:output split; a single
# constant makes that a one-line change instead of re-deriving every multiplier.
OUTPUT_TOKEN_SHARE = 0.25

# What to bill for a model that is not in the price table.
#
# A real trade-off, made deliberately:
#   - 1.0 (today's behavior) is exactly the bug this commit fixes. An unknown id
#     silently billing at the baseline is how claude-sonnet-4-6 undercharges ~20x.
#     The failure is invisible and always favors the wrong direction.
#   - Raising is worse. credit_multiplier runs inside chat_v3._finalize, which is
#     what SAVES a partial answer when a student's browser disconnects mid-turn.
#     An exception there loses work the student already paid tokens for — punishing
#     a student for an operator's missing table row.
# So: a conservative constant plus a loud ERROR log. 4.0 is deliberately not a new
# pricing regime — it is the rate the incumbent default (gemini-3.5-flash) billed
# at before this change, so an unknown model bills like the model we were already
# charging everyone for. It errs away from undercharging without inventing a
# punitive 20x for what is usually a typo in DOTHESIS_AGENT_MODEL.
#
# The real defense is upstream: test_credit_multiplier.py asserts every id the
# resolvers can pick by default is priced, so this fires on operator error (a hand-
# set env var, an OpenRouter cascade to an unlisted fallback) — never on a default.
UNKNOWN_MODEL_MULTIPLIER = 4.0

log = logging.getLogger(__name__)


def _blended_price(model: str) -> float | None:
    """The model's $/1M tokens collapsed to one number at DoThesis's token mix.
    None when unpriced, so the caller can tell "free" from "unknown"."""
    p = MODEL_PRICES.get(model)
    if not p:
        return None
    return (1.0 - OUTPUT_TOKEN_SHARE) * p["in"] + OUTPUT_TOKEN_SHARE * p["out"]


# Single source of truth for how credits scale with the active model: pricier models
# must scale up or we undercharge. Used by BOTH charge sites — the interactive chat
# turn (chat_v3._finalize) and the auto-draft run (job_runner._charge_auto_run) — so
# they can't drift apart.
#
# Prices come from quality/model_prices.py — a dated table whose Ofox rows are live
# rates pulled from the gateway. This function used to infer price from SUBSTRINGS of
# the model id ("pro" -> 5.0, "flash" -> 1.0, else 1.0), which encoded Gemini's naming
# as if it were a pricing schema. It misfired on every real id from both routes:
# claude-sonnet-4-6 matched nothing and billed 1.0 against a ~20x true cost (and
# _default_model selects it AUTOMATICALLY once ANTHROPIC_API_KEY exists);
# deepseek-v4-pro billed 5.0 for containing "pro" while costing ~2x; qwen-max billed
# 1.0 against ~2.3x. A name is not a price, and no amount of extra branches makes it
# one — the next model id breaks the next guess. Reading the table cannot misfire on
# a name it has never seen; it can only be missing an entry, which is loud (above).
#
# Same principle as d4382a6 and e3cb9c6: bill from what is RECORDED, never from what
# can be INFERRED.
def credit_multiplier(model: str) -> float:
    price = _blended_price(model or "")
    if price is None:
        # ERROR, not WARNING: billing an unpriced model is an operator error that
        # silently moves money. A quiet fallback is how the bug this replaces lived.
        log.error(
            "credit_multiplier: model %r is not in quality/model_prices.py — billing "
            "at the %.1fx fallback. Add it to the table.", model, UNKNOWN_MODEL_MULTIPLIER,
        )
        return UNKNOWN_MODEL_MULTIPLIER
    # Divide rather than store per-model constants so the baseline is 1.0 by
    # construction and can never drift from the model it is defined against.
    return price / _blended_price(BASELINE_MODEL)
