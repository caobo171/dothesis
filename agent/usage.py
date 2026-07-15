"""Route-independent token accounting.

The credit ledger (chat_v3) debits per token, so usage must be read the same way
whether the model is native (LangChain surfaces `usage_metadata` on the AIMessage)
or OpenAI-compatible via OpenRouter (`usage.prompt_tokens` / `usage.completion_tokens`
on the payload/chunk). One extractor keeps billing correct no matter which provider
actually served the turn.
"""
from __future__ import annotations


def _cached(details, *keys) -> int:
    """Read a cached-input count out of a provider's token-details blob.

    Clamped to >= 0 and coerced to int here rather than at each call site: the
    value flows into arithmetic (and one day a ledger column), so a None or a
    negative from a provider must never escape this module.
    """
    if not isinstance(details, dict):
        return 0
    for k in keys:
        if k in details:
            try:
                return max(0, int(details.get(k) or 0))
            except (TypeError, ValueError):
                return 0
    return 0


def extract_usage(obj) -> dict:
    """Normalize any provider's usage payload to `{"in", "out", "cached_in"}`.

    Order matters: LangChain's `usage_metadata` (native route) is checked first
    because native messages may also carry a raw `usage` blob; usage_metadata is
    the normalized, provider-agnostic one. Falls back to the OpenAI-compatible
    `usage` shape (dict key or attribute), and to zeros when nothing is present.

    `cached_in` is a SUBSET of `in`, never additional to it — verified against both
    shapes: OpenAI-compat reports prompt_tokens=3456 alongside
    prompt_tokens_details.cached_tokens=3328 (measured on Ofox/qwen-plus
    2026-07-16, reproduce via scripts/probe_prompt_cache.py), and LangChain defines
    input_tokens as the sum of all input token types, cache_read included. So
    `in - cached_in` is the uncached remainder; adding them double-counts.

    BILLING IS DELIBERATELY UNCHANGED: callers still debit `in` at full rate. This
    key exists so the discount can be MEASURED before anyone decides whether to
    pass it on — that is a pricing decision, not a side effect of an extractor.
    Additive by design: existing readers of `in`/`out` keep working untouched.
    """
    if obj is None:
        return {"in": 0, "out": 0, "cached_in": 0}
    um = getattr(obj, "usage_metadata", None)
    if isinstance(um, dict) and um:
        _in = int(um.get("input_tokens", 0) or 0)
        return {"in": _in,
                "out": int(um.get("output_tokens", 0) or 0),
                # LangChain nests cache stats under input_token_details.cache_read.
                "cached_in": min(_cached(um.get("input_token_details"), "cache_read"), _in)}
    usage = obj.get("usage") if isinstance(obj, dict) else getattr(obj, "usage", None)
    if isinstance(usage, dict):
        # OpenAI names them prompt/completion; some providers echo Anthropic's
        # input/output — accept either so no route silently reports zero.
        _in = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        # prompt_tokens_details.cached_tokens is the OpenAI-compat spelling; the
        # flat aliases are what some gateways emit instead (same set
        # scripts/probe_prompt_cache.py accepts — keep the two in step).
        c = _cached(usage.get("prompt_tokens_details"), "cached_tokens") or _cached(
            usage, "cached_tokens", "cache_read_input_tokens", "prompt_cache_hit_tokens")
        return {"in": _in,
                "out": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
                # Clamped to `in`: a provider over-reporting cache must not make the
                # uncached remainder negative for whatever prices this later.
                "cached_in": min(c, _in)}
    return {"in": 0, "out": 0, "cached_in": 0}
