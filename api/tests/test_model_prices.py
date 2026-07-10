"""Price table + cost() (F9 Task 1). Pure arithmetic against a hand-maintained
table — no network. Pins the cost math, the unknown-model contract, and that the
candidate models we care about are present."""
from quality.model_prices import cost, MODEL_PRICES


def test_cost_math():
    # 1M in + 1M out at ($0.33, $1.95) = 2.28
    assert abs(cost("qwen3.6-plus", 1_000_000, 1_000_000) - 2.28) < 1e-6


def test_unknown_model_is_none():
    assert cost("does-not-exist", 100, 100) is None


def test_candidates_present():
    for m in ("gemini-3.5-flash", "qwen3.6-plus", "gpt-5.4-mini"):
        assert m in MODEL_PRICES
