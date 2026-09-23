"""Pricing config: credit packs, paper-cost matrix, tier→model resolution.

PACKAGES values come directly from Survify's PRICING_PACKAGES (USD prices,
credits per pack), and as of 2026-09-14 so does the credit UNIT they are
denominated in — see the block above CREDITS_PER_AUTO_THESIS. PAPER_COST is a
placeholder matrix; tune later.
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


# --- the credit unit --------------------------------------------------------
#
# Re-based 2026-09-14 onto Survify's credit scale, so the two products that sell
# the same DoThesis engine quote a student the same numbers. Survify prices a
# full report at 600 credits (chapters 90+140+120+140+110 in fillform's
# backend/src/config/brand/survify.ts, `pricing.dothesis.chapters`) and sells
# 300/700/2000-credit packs. DoThesis called the identical run 10,000 credits and
# sold 10k/25k/60k packs. Same engine, same tokens — only the unit differed, and
# one product quoting two different units is how a student gets two prices.
#
# The constants below are derived from each other DELIBERATELY. This file used to
# carry the pack anchor (CREDITS_PER_AUTO_THESIS) and the billing rate (a bare
# `/ 1000` inlined at both charge sites) as unrelated literals, so the credit page
# could promise "this pack is one thesis" while billing debited something else
# entirely. That is precisely the drift the long ⚠️ block that used to live here
# was reporting. Deriving the rate from the anchor makes it unrepresentable.
CREDITS_PER_AUTO_THESIS = 600           # Survify's full-report price, verbatim
TOKENS_PER_AUTO_THESIS = 10_000_000     # measured size of one run; unchanged
TOKENS_PER_CREDIT = TOKENS_PER_AUTO_THESIS // CREDITS_PER_AUTO_THESIS  # 16,666

# What a credit costs, and what it sells for.
#
# Cost per credit is model-INDEPENDENT by construction: a charge is
# tokens / TOKENS_PER_CREDIT * credit_multiplier(m), and credit_multiplier divides
# by the BASELINE model's blended price, so the served model cancels out of
# dollars-per-credit completely. Switching brains moves how many credits a run
# debits; it cannot move the margin.
#
#   cost/credit = TOKENS_PER_CREDIT * blended(BASELINE_MODEL) / 1e6
#               = 16,666 * $0.85/1M = $0.0142
#
#   Starter   $9 /  300 = $0.0300/credit -> 53% margin
#   Pro      $19 /  700 = $0.0271/credit -> 48% margin
#   Power    $49 / 2000 = $0.0245/credit -> 42% margin
#
# ⚠️ Thinner than the 66/63/61% the old 10,000-credit packs were sized for, and
# that is the actual price of matching Survify rather than a regression to fix.
# Nothing about the engine got cheaper or dearer — a full run still burns ~$8.50
# of baseline tokens — but Survify sells that run for ~$16 (600 credits at the Pro
# rate) where DoThesis was asking ~$25. If the margin has to come back, raise the
# pack DOLLARS; raising the credit counts would just re-break parity with Survify.
#
# Production bills well UNDER the anchor. The configured default is gpt-6-luna
# ($0.10/$0.50, 2026-09-23) = 0.24x baseline, so a real 10M-token run
# debits ~141 credits, not 600. The anchor stays at Survify's 600 so the credit
# page under-promises: a student is never told "this pack is one thesis" and then
# blocked mid-run. Re-tune from token_ledger once it reports real tokens/run.


PACKAGES: list[Package] = [
    # Survify's `packages` array, field for field — fillform/frontend/config/brand/
    # survify.ts:94-122, mirrored server-side in backend/src/api/routes/order/
    # polar.ts:8-12. Names included: Survify calls these Starter/Pro/Power, and a
    # student comparing the two products should not see two different ladders.
    {
        "id": "starter_package",
        "name": "Starter",
        "price_cents": 900,        # $9  → $0.0300/credit, ~53% margin
        "old_price_cents": 1500,   # $15
        "credits": 300,            # ≈ half an Auto Thesis run at the anchor
    },
    {
        "id": "standard_package",
        "name": "Pro",
        "price_cents": 1900,       # $19 → $0.0271/credit, ~48% margin
        "old_price_cents": 3500,   # $35
        "credits": 700,            # ≈ one full run, with headroom
    },
    {
        "id": "expert_package",
        "name": "Power",
        "price_cents": 4900,       # $49 → $0.0245/credit, ~42% margin
        "old_price_cents": 10000,  # $100
        "credits": 2000,           # ≈ 3.3 runs
    },
]

PACKAGES_BY_ID: dict[str, Package] = {p["id"]: p for p in PACKAGES}


# Re-denominated into the new credit unit with the 2026-09-14 re-base. Survify
# prices no standalone paper, so there is no number to copy here — these are the
# OLD figures divided by 15, which keeps every ratio in the matrix exactly intact
# (premium = 2.5x standard, each level = 2x the one below) while landing on round
# integers. 15 rather than the unit's true 16.67 for that roundness; the ~11%
# it leaves on the table errs toward charging more, which is the safe direction
# for a matrix whose own docstring still calls it a placeholder.
PAPER_COST: dict[tuple[str, str], int] = {
    ("research", "standard"):  4, ("research", "premium"): 10,
    ("bachelor", "standard"):  8, ("bachelor", "premium"): 20,
    ("master",   "standard"): 16, ("master",   "premium"): 40,
    ("phd",      "standard"): 32, ("phd",      "premium"): 80,
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
# THE UNIT IS A LOOKUP. One CrossRef query = 3 credits (~$0.09 at Starter pack
# rates), so checking a 40-entry reference list costs 120 credits (~$3.60) and
# checking one reference costs 3. That keeps the price proportional to the work
# without needing a second pricing concept, and it is explainable to a student:
# you pay per source we go and check.
#
# 3 is Survify's `citationPerSource`, taken verbatim rather than re-derived — the
# 2026-09-14 re-base makes the two products' credits the same size, so Survify's
# number is directly usable and picking our own would only reintroduce the drift.
TOOL_COST_PER_UNIT: dict[str, int] = {
    # per CrossRef lookup
    "verify-citation":  3,
    "verify-citations": 3,
    # per distinct source resolved out of the document (phase A). Phase B's
    # model calls are billed on tokens on top of this.
    "cite-docx":        3,
}

TOOL_COST_FLAT: dict[str, int] = {
    # Local stylometry, no network, no model. Priced as a token gesture rather
    # than free, so the run appears in the ledger like every other one. Left at 1
    # through the re-base: the new credit is worth ~12x the old one, so 1 is now a
    # ~$0.03 gesture instead of a ~$0.0025 rounding error — which is what "token
    # gesture" was always reaching for. Scaling it up would make it a real fee.
    "writing-rhythm":   1,
    # A vendor similarity check is the one tool with a real per-call invoice
    # attached. Charged only on a successful check — an unconfigured deployment
    # returns provider_not_configured and must not bill for a check it did not
    # perform. 50 is Survify's `plagiarismPrice`, verbatim. The old 5 was 5 credits
    # of the OLD unit — about $0.01 against a vendor bill, which the note below
    # already flagged as shape-not-margin.
    "plagiarism-check": 50,
    # The DOCUMENT self-check: no model, no vendor, pure CPU over the student's
    # own file. Priced like writing-rhythm — a token amount so the run lands in
    # the ledger — NOT like plagiarism-check, which carries a real vendor
    # invoice. When a provider is configured the run also pays that; see
    # similarity-docx-corpus below.
    "similarity-docx":  2,
    # The surcharge when a corpus provider actually ran. Separate from the base
    # so an unconfigured deployment charges 2, not 52, for the half it performed.
    # Tracks plagiarism-check because it buys the same thing — one vendor call —
    # so 2 + 50 lands a corpus-backed check a hair above the dedicated tool, the
    # same ordering the old 2 + 5 vs 5 had.
    "similarity-docx-corpus": 50,
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
    "extract-text", "scan-docx", "scan-cite-docx", "scan-similarity-docx",
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


def is_priced(model: str) -> bool:
    """Does quality/model_prices.py carry a real rate for this exact id?

    Exists for the one caller that gets to CHOOSE which id a ledger row is
    labelled with — headless_entry._UsageMeter picks between the model that
    SERVED a step and the model the run was CONFIGURED with. It has to ask the
    question with the same lookup `credit_multiplier` will use, or the two
    disagree and the row it deemed "priced" bills at UNKNOWN_MODEL_MULTIPLIER
    anyway. False here is exactly the condition for that fallback, by
    construction — there is no second table and no second predicate.
    """
    return _blended_price(model or "") is not None


# Single source of truth for how credits scale with the active model: pricier models
# must scale up or we undercharge. Used by BOTH charge sites — the interactive chat
# turn (chat_v3._finalize) and the Auto Thesis run (job_runner._charge_auto_thesis_run) — so
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
