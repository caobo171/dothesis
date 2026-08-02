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
    # M2 citation planner (orchestrator/tools/m2_literature._engine_model), pinned
    # by CITATION_PLANNER_MODEL. Rate read off ai.google.dev/gemini-api/docs/pricing
    # on 2026-08-02: $0.50 in (text/image/video) / $3.00 out, standard tier.
    # Blends to ~4.29x baseline vs the 1.00x the old gemini-2.5-flash planner cost.
    "gemini-3-flash-preview": {"in": 0.50, "out": 3.00, "provider": "google",
                               "note": "M2 citation planner; needs raw generate_content()",
                               "updated": "2026-08-02"},
    # BASELINE_MODEL — its blended price is the denominator of EVERY multiplier, so
    # this row sets the dollar value of a credit. Corrected 2026-08-02 from the old
    # $0.15/$0.60 to Google's published $0.30/$2.50 (ai.google.dev/gemini-api/docs/pricing).
    #
    # This was not a judgement call: two other parts of the pricing system were
    # ALREADY calibrated against $0.30/$2.50, and only this row disagreed.
    #   - PACKAGES documents "~66% margin" on the starter pack. Cost per pack is
    #     credits * 1000 * blended(baseline) / 1e6 — the served model cancels out —
    #     so $24.99/10000 credits gives 66.0% at this row's price and 89.5% at the
    #     old one. The packs were sized on THIS number.
    #   - UNKNOWN_MODEL_MULTIPLIER = 4.0 is documented as "the rate the incumbent
    #     default (gemini-3.5-flash) billed at". That is 3.97x against this row and
    #     12.86x against the old one.
    # So the old row was making every multiplier ~3.24x too large and quietly
    # billing students at ~89% margin instead of the intended ~66%.
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "provider": "google",
                         "note": "BASELINE (1.0x by construction); cheap, weaker instruction-following",
                         "updated": "2026-08-02"},
    # OpenAI DIRECT rate, post the 2026-07-30 80% cut ($1.00/$6.00 -> $0.20/$1.20).
    # Keyed on the bare id because that is what route=openai puts on the wire;
    # the provider-prefixed "openai/gpt-5.6-luna" row below is Ofox's RESALE of
    # the same model, still at the pre-cut launch price. Two ids, two real
    # prices, 5x apart — which is exactly why MODEL_PRICES is keyed by the id
    # actually sent rather than by model family.
    "gpt-5.6-luna": {"in": 0.20, "out": 1.20, "provider": "openai",
                     "note": "configured default (route=openai); 1.05M ctx, vision, tools",
                     "updated": "2026-08-02"},
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
    # Priced because agent/runtime.py::_default_model and model_factory.spec_from_env
    # switch to this AUTOMATICALLY the moment ANTHROPIC_API_KEY lands — no deploy, no
    # code change. Absent from the table it billed at the unknown-model fallback while
    # actually costing ~20x baseline. Anthropic list price, verified 2026-07-15.
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "provider": "anthropic",
                          "note": "architecture's preferred brain; auto-selected when ANTHROPIC_API_KEY is set",
                          "updated": "2026-07-15"},
    # The thread_namer's cheap tier (api/app/thread_namer.py). Both this table's
    # sources and engine/utils/model_config.py agree on 0.10/0.40, so there is no
    # conflict to resolve here — unlike the 3.5-flash row above.
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40, "provider": "google",
                              "note": "cheapest Gemini; thread-naming tier", "updated": "2026-07-15"},
    # --- Ofox gateway ids + LIVE prices pulled from GET api.ofox.ai/v1/models
    #     (the `pricing` field, 2026-07-10). Keys match the provider/model string
    #     passed to evaluate_models, so cost() resolves them directly. ---
    "google/gemini-3.5-flash": {"in": 1.50, "out": 9.00, "provider": "ofox",
                                "note": "current default; output tripled", "updated": "2026-07-10"},
    "google/gemini-2.5-flash": {"in": 0.30, "out": 2.50, "provider": "ofox",
                                "note": "cheap Gemini; weaker markers", "updated": "2026-07-10"},
    "bailian/qwen-plus": {"in": 0.12, "out": 0.29, "provider": "ofox",
                          "note": "configured default; VN leader + markers + tools; 1M ctx", "updated": "2026-07-10"},
    # Rates read live from the Ofox /v1/models catalogue on 2026-08-02 (prompt
    # 1e-6, completion 6e-6 per token), not from web research — this row exists
    # because the model is now the configured default and an unpriced default is
    # exactly the silent-undercharge failure UNKNOWN_MODEL_MULTIPLIER guards.
    # Blends to ~8.6x baseline, so it would have billed at the 4.0x fallback —
    # under-charging by ~2.1x on every turn.
    "openai/gpt-5.6-luna": {"in": 1.00, "out": 6.00, "provider": "ofox",
                            "note": "configured default; 1.05M ctx, vision, tools, reasoning",
                            "updated": "2026-08-02"},
    "bailian/qwen-flash": {"in": 0.022, "out": 0.22, "provider": "ofox",
                           "note": "cheapest Qwen; 1M ctx", "updated": "2026-07-10"},
    "bailian/qwen-max": {"in": 0.35, "out": 1.38, "provider": "ofox",
                         "note": "strongest Qwen BUT only 32k ctx (risky for DoThesis)", "updated": "2026-07-10"},
    "deepseek/deepseek-v4-flash": {"in": 0.14, "out": 0.28, "provider": "ofox",
                                   "note": "cheapest that passed markers+VN+tools; 1M ctx", "updated": "2026-07-10"},
    "deepseek/deepseek-v4-pro": {"in": 0.45, "out": 0.88, "provider": "ofox",
                                 "note": "stronger DeepSeek; 1M ctx", "updated": "2026-07-10"},
    "z-ai/glm-5": {"in": 1.00, "out": 3.20, "provider": "ofox",
                   "note": "over-thinks; FAILED [OPTIONS] marker in live probe", "updated": "2026-07-10"},
}


def cost(model: str, in_tokens: int, out_tokens: int) -> float | None:
    """True per-task cost = tokens x price table. None for an unknown model so
    callers can distinguish "free" from "unpriced"."""
    p = MODEL_PRICES.get(model)
    if not p:
        return None
    return round(in_tokens / 1_000_000 * p["in"] + out_tokens / 1_000_000 * p["out"], 6)
