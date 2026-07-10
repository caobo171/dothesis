"""Dated $/1M-token price table for candidate central-brain models + a cost helper.
Hand-maintained — update the numbers and `updated` when prices move (they do, monthly).
Sources: July-2026 pricing research (OpenRouter / provider pages)."""
from __future__ import annotations

# in/out = USD per 1,000,000 tokens.
MODEL_PRICES: dict[str, dict] = {
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00, "provider": "google",
                         "note": "current default; output tripled in 2026", "updated": "2026-07-08"},
    # Ofox-indicative rates (2026-07 web research — VERIFY on ofox.ai/pricing before
    # relying on it). Output is ~15x cheaper than 3.5-flash's $9/M — the dominant
    # lever, since output is uncacheable. Weaker instruction-following than 3.5:
    # must clear the marker floor (run the shootout) before switching.
    "gemini-2.5-flash": {"in": 0.15, "out": 0.60, "provider": "google",
                         "note": "cheap; weaker instruction-following; via Ofox google/gemini-2.5-flash",
                         "updated": "2026-07-10"},
    "gpt-5.4-mini": {"in": 0.40, "out": 1.75, "provider": "openai",
                     "note": "safe western drop-in", "updated": "2026-07-08"},
    # in=0.33 (not 0.325): the plan's table snippet and its cost test disagreed
    # (0.325 vs a "$0.33 => 2.28" comment/test); reconciled to 0.33 so the table,
    # the comment, and the test are internally consistent.
    "qwen3.6-plus": {"in": 0.33, "out": 1.95, "provider": "openrouter",
                     "note": "SEA-HELM Vietnamese leader; 1M ctx", "updated": "2026-07-08"},
    "deepseek-v4-flash": {"in": 0.09, "out": 0.18, "provider": "openrouter",
                          "note": "cheapest; reliability/VN unproven", "updated": "2026-07-08"},
    "glm-5.2": {"in": 1.40, "out": 4.40, "provider": "openrouter",
                "note": "over-thinks; output tokens balloon", "updated": "2026-07-08"},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "provider": "anthropic",
                         "note": "strong agentic, mid-price", "updated": "2026-07-08"},
}


def cost(model: str, in_tokens: int, out_tokens: int) -> float | None:
    """True per-task cost = tokens x price table. None for an unknown model so
    callers can distinguish "free" from "unpriced"."""
    p = MODEL_PRICES.get(model)
    if not p:
        return None
    return round(in_tokens / 1_000_000 * p["in"] + out_tokens / 1_000_000 * p["out"], 6)
