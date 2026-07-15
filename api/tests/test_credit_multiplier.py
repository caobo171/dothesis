"""credit_multiplier() must price a model from the TABLE, not from its NAME.

The multiplier scales credits by how expensive the active model is relative to
the gemini-2.5-flash baseline. It used to infer that from substrings of the model
id ("pro" -> 5.0, "flash" -> 1.0, else 1.0), which is Gemini-shaped and misfires
on every non-Gemini id both routes can now produce. Each case below is a verified
misfire, priced against quality/model_prices.py.
"""
import math

import pytest

from app.pricing import BASELINE_MODEL, OUTPUT_TOKEN_SHARE, credit_multiplier
from quality.model_prices import MODEL_PRICES


def _expected(model: str) -> float:
    """Re-derive the multiplier from the table, independently of pricing.py's
    implementation, so these tests fail on a WRONG NUMBER rather than merely
    restating whatever the code computes."""
    p, base = MODEL_PRICES[model], MODEL_PRICES[BASELINE_MODEL]
    w_in = 1.0 - OUTPUT_TOKEN_SHARE

    def blended(x):
        return w_in * x["in"] + OUTPUT_TOKEN_SHARE * x["out"]

    return blended(p) / blended(base)


def test_baseline_is_exactly_one():
    """gemini-2.5-flash is the definitional baseline — the credit rate (1 credit
    ~ 1000 tokens) is calibrated on it. Anything but 1.0 here reprices everything."""
    assert credit_multiplier("gemini-2.5-flash") == 1.0


def test_claude_sonnet_is_not_billed_as_baseline():
    """THE URGENT ONE. agent/runtime.py::_default_model switches to Claude the
    moment ANTHROPIC_API_KEY lands — no code change, no deploy. The name carries
    no "pro"/"flash" substring, so it fell through to 1.0 and undercharged ~20x.
    """
    m = credit_multiplier("claude-sonnet-4-6")
    assert m > 15.0, f"claude-sonnet-4-6 must not bill near baseline, got {m}"
    assert math.isclose(m, _expected("claude-sonnet-4-6"), rel_tol=1e-6)


def test_deepseek_v4_pro_is_not_billed_as_a_pro_tier():
    """"pro" is a substring of "deepseek-v4-pro", so it billed at Gemini-Pro's
    5.0 while actually costing near baseline — a ~2.4x OVERCHARGE to students."""
    m = credit_multiplier("deepseek/deepseek-v4-pro")
    assert m < 3.0, f"deepseek-v4-pro is not a Gemini Pro tier, got {m}"
    assert math.isclose(m, _expected("deepseek/deepseek-v4-pro"), rel_tol=1e-6)


def test_qwen_max_is_not_billed_as_baseline():
    """No Gemini substring -> fell through to 1.0, but qwen-max blends ~2.3x."""
    m = credit_multiplier("bailian/qwen-max")
    assert m > 2.0, f"qwen-max must not bill at baseline, got {m}"
    assert math.isclose(m, _expected("bailian/qwen-max"), rel_tol=1e-6)


def test_ofox_gemini_25_flash_bills_the_gateway_rate_not_the_native_rate():
    """The Ofox gateway resells gemini-2.5-flash at 0.30/2.50, NOT Google's
    0.15/0.60 (live rates pulled from the gateway, quality/model_prices.py).
    Substring matching saw "flash" and billed 1.0 — reading the baseline's native
    price for a gateway id that costs several times more. This is the route the
    ofox migration makes the default, so it undercharges on the live config.
    """
    m = credit_multiplier("google/gemini-2.5-flash")
    assert m > 2.0, f"the Ofox resale of 2.5-flash is not the baseline, got {m}"
    assert math.isclose(m, _expected("google/gemini-2.5-flash"), rel_tol=1e-6)


def test_every_model_a_resolver_can_pick_by_default_is_priced():
    """Guard the unknown-model fallback from ever firing on a DEFAULT.

    The fallback is a safety net, not a pricing strategy — it must never be how a
    model the code picks on its own gets billed. These are the ids
    agent/model_factory.py::spec_from_env and orchestrator/llm.py resolve with no
    env set; adding a new default without a price now fails here, in CI, instead
    of silently mispricing production.
    """
    for model in ("gemini-3.5-flash", "claude-sonnet-4-6", "google/gemini-2.5-flash",
                  "gemini-2.5-flash"):
        assert model in MODEL_PRICES, f"{model} is a resolver default but has no price"


@pytest.mark.parametrize("unknown", ["", "not-a-real-model", "totally/made-up-v9"])
def test_unknown_model_bills_conservatively_and_never_raises(unknown):
    """An id absent from the table must not bill at the baseline — silently
    charging 1.0 for an unknown expensive model IS the claude-sonnet-4-6 bug.

    It must also not RAISE: this runs inside the chat turn's _finalize, where an
    exception loses the student's answer. So: a conservative constant + a loud
    log, never an exception. See pricing.py for the full justification.
    """
    from app.pricing import UNKNOWN_MODEL_MULTIPLIER

    assert credit_multiplier(unknown) == UNKNOWN_MODEL_MULTIPLIER
    assert UNKNOWN_MODEL_MULTIPLIER > 1.0, "unknown must not bill at the baseline"


def test_unknown_model_logs_loudly(caplog):
    """The fallback must be visible in prod — a silent fallback is how the
    current bug survived. Billing an unpriced model is an operator error."""
    import logging

    with caplog.at_level(logging.ERROR, logger="app.pricing"):
        credit_multiplier("some-unpriced-model")
    # getMessage() renders the lazy %-args the logger was called with.
    assert any("some-unpriced-model" in r.getMessage() for r in caplog.records), \
        "unknown model must be logged at ERROR with the offending id"


def test_multiplier_is_monotonic_in_price():
    """The property that must hold whatever the numbers become: a model that
    costs more per token than another must never bill for less."""
    priced = [(m, credit_multiplier(m)) for m in MODEL_PRICES]
    w_in = 1.0 - OUTPUT_TOKEN_SHARE
    for model, mult in priced:
        p = MODEL_PRICES[model]
        blended = w_in * p["in"] + OUTPUT_TOKEN_SHARE * p["out"]
        for other, other_mult in priced:
            q = MODEL_PRICES[other]
            other_blended = w_in * q["in"] + OUTPUT_TOKEN_SHARE * q["out"]
            if blended > other_blended:
                assert mult > other_mult, f"{model} costs more than {other} but bills less"
