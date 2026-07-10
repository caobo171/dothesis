"""Route-independent token accounting.

The credit ledger (chat_v3) debits per token, so usage must be read the same way
whether the model is native (LangChain surfaces `usage_metadata` on the AIMessage)
or OpenAI-compatible via OpenRouter (`usage.prompt_tokens` / `usage.completion_tokens`
on the payload/chunk). One extractor keeps billing correct no matter which provider
actually served the turn.
"""
from __future__ import annotations


def extract_usage(obj) -> dict:
    """Normalize any provider's usage payload to `{"in": int, "out": int}`.

    Order matters: LangChain's `usage_metadata` (native route) is checked first
    because native messages may also carry a raw `usage` blob; usage_metadata is
    the normalized, provider-agnostic one. Falls back to the OpenAI-compatible
    `usage` shape (dict key or attribute), and to zeros when nothing is present.
    """
    if obj is None:
        return {"in": 0, "out": 0}
    um = getattr(obj, "usage_metadata", None)
    if isinstance(um, dict) and um:
        return {"in": int(um.get("input_tokens", 0) or 0),
                "out": int(um.get("output_tokens", 0) or 0)}
    usage = obj.get("usage") if isinstance(obj, dict) else getattr(obj, "usage", None)
    if isinstance(usage, dict):
        # OpenAI names them prompt/completion; some providers echo Anthropic's
        # input/output — accept either so no route silently reports zero.
        return {"in": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                "out": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)}
    return {"in": 0, "out": 0}
