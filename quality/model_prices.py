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
