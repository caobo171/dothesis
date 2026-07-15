#!/usr/bin/env python3
"""Does our prompt prefix actually get cached on a given route?

WHY THIS EXISTS
---------------
NOT to decide the route. That question is already settled by `quality/model_prices`:
bailian/qwen-plus is $0.12/M input vs gemini-3.5-flash's $1.50/M — a 12.5x gap. A
perfect prompt cache is only a ~10x input discount, so it CANNOT close a gap wider
than itself. qwen-plus with no cache beats gemini-3.5-flash with a perfect cache
(~$0.013 vs ~$0.021 on a 30-turn chat's re-sent SYSTEM_PROMPT). Cache absence does
not threaten the qwen decision.

This exists for BILLING PRECISION. `agent/usage.extract_usage` feeds the credit
ledger. It now preserves `cached_in`, but no billing arithmetic prices it yet — so
a cached turn is still charged at full input rate. Note this is NOT the same as
`job_runner.py:373`-style bugs, which billed for a model that never ran and were
unambiguously wrong; passing a received cache discount on to students is a pricing
POLICY decision, not a defect. This probe supplies the measurement that decision
needs. Pricing it requires a cached dimension on `quality/model_prices.cost()` and
a place to record it on `TokenLedger`.

ANSWERED for bailian/qwen-plus on 2026-07-16: Ofox's OpenAI-compat endpoint DOES
cache. 3328/3456 input tokens (96%) were served from cache on turn 2 against the
real SYSTEM_PROMPT. `agent/model_factory._ofox` previously warned the opposite
("may NOT get the ~90% input cache discount here") — that caveat was disproven by
this script and has been replaced with the measurement.

The result stands for qwen-plus only. Re-run this for any other model or route
before assuming it caches; that is what the --model flag is for.

Nothing ELSE in the repo can measure this, which is why this script exists rather
than a test:

  - `agent/usage.py:extract_usage` normalizes every provider to {"in", "out"} and
    DISCARDS the cache fields (`input_token_details.cache_read` on native,
    `prompt_tokens_details.cached_tokens` on OpenAI-compat).
  - `quality/model_prices.cost(model, in_tokens, out_tokens)` has no cached-token
    dimension, so it cannot price the difference.
  - `quality/model_eval._complete` is single-shot. The first call to any prefix is
    a cache WRITE, never a read — a one-shot probe cannot observe a hit by
    construction.

The `a070354` benchmark measured OUTPUT cost. Caching is an INPUT-side effect, so
that result neither confirms nor denies a cache — the two are orthogonal. Both
point the same way for the route choice; only the billing question is open.

WHAT THIS DOES
--------------
Speaks raw HTTP to the gateway — deliberately NOT through LangChain — so we see the
gateway's ground truth rather than whatever our stack preserves. Two calls that
mirror a real chat:

    call 1:  [system, user1]                        <- cache write
    call 2:  [system, user1, assistant1, user2]     <- shared prefix, should read

The shared prefix is the real `agent.runtime.SYSTEM_PROMPT`, because that is the
exact text whose cacheability is in question. A synthetic filler prompt would prove
nothing about production.

Reads the raw `usage` blob verbatim. Any nonzero cached-token count on call 2 means
the route caches; zero across both means it does not (or the prefix is under the
provider's cache minimum — see PREFIX SIZE below).

PREFIX SIZE
-----------
OpenAI-style auto-caching typically ignores prefixes under ~1024 tokens. The script
prints the prompt-token count so a zero result can be read correctly: zero cached on
a 4k-token prefix is a real negative; zero cached on an 800-token prefix is
inconclusive. It does NOT auto-pad — padding would measure a prompt we do not ship.

USAGE
-----
    export OFOX_API_KEY=...
    ./run.sh python ../scripts/probe_prompt_cache.py                  # from api/
    python scripts/probe_prompt_cache.py --model bailian/qwen-plus    # from root

    --model   gateway model id (default: bailian/qwen-plus — the id the route
              actually serves, per agent/model_factory.spec_from_env and
              quality/model_prices. A default that names a model we do not run
              would measure something other than the 96% cache result recorded
              in agent/model_factory._ofox, while looking like a reproduction.)
    --base    gateway base url (default: https://api.ofox.ai/v1)
    --json    emit machine-readable JSON only

Costs two real calls. Needs gateway balance.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _system_prompt() -> str:
    """The real production prefix, or a loud failure.

    Importing agent.runtime pulls the deepagents stack. If that import breaks, we
    must NOT quietly fall back to a placeholder — a cache result measured against
    the wrong text is worse than no result, because it looks authoritative.
    """
    from agent.runtime import SYSTEM_PROMPT
    return SYSTEM_PROMPT


def _cached_in(usage: dict) -> int | None:
    """Pull the cached-input count out of whatever shape the gateway returned.

    Returns None when no cache field is present at all — which is itself the
    finding (the provider isn't reporting cache stats), and is distinct from a
    reported zero (cache supported, prefix missed).
    """
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and "cached_tokens" in details:
        return int(details.get("cached_tokens") or 0)
    # Some gateways flatten it; accept the common aliases rather than miss a hit.
    for key in ("cached_tokens", "cache_read_input_tokens", "prompt_cache_hit_tokens"):
        if key in usage:
            return int(usage.get(key) or 0)
    return None


def _post(base: str, key: str, model: str, messages: list[dict]) -> dict:
    import httpx

    r = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": messages,
            # Keep output tiny: we are measuring input-side caching, and output
            # tokens are the expensive part of a probe we may run repeatedly.
            "max_tokens": 16,
            "temperature": 0,
        },
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Must match the configured Ofox id (agent/model_factory.spec_from_env's ofox
    # default), or a re-run silently probes a different/nonexistent model than the
    # cache figure documented in agent/model_factory._ofox was taken on.
    ap.add_argument("--model", default="bailian/qwen-plus")
    ap.add_argument("--base", default=os.getenv("DOTHESIS_EVAL_BASE_URL", "https://api.ofox.ai/v1"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    key = os.getenv("OFOX_API_KEY") or os.getenv("DOTHESIS_EVAL_API_KEY")
    if not key:
        print("OFOX_API_KEY (or DOTHESIS_EVAL_API_KEY) is not set — nothing was measured.",
              file=sys.stderr)
        return 2

    system = _system_prompt()
    out = print if not args.json else (lambda *a, **k: None)

    out(f"route  : {args.base}")
    out(f"model  : {args.model}")
    out(f"prefix : agent.runtime.SYSTEM_PROMPT ({len(system)} chars)")
    out("")

    # Turn 1: the cache write.
    m1 = [{"role": "system", "content": system},
          {"role": "user", "content": "In one sentence: what is my next step?"}]
    r1 = _post(args.base, key, args.model, m1)
    u1 = r1.get("usage") or {}
    a1 = (r1["choices"][0]["message"].get("content") or "").strip()

    # Turn 2: identical prefix + the turn-1 exchange, exactly as a real second chat
    # turn would arrive. This is what must hit cache for the economics to hold.
    m2 = m1 + [{"role": "assistant", "content": a1},
               {"role": "user", "content": "Thanks — and in one sentence, why that step?"}]
    r2 = _post(args.base, key, args.model, m2)
    u2 = r2.get("usage") or {}

    c1, c2 = _cached_in(u1), _cached_in(u2)

    if args.json:
        print(json.dumps({"model": args.model, "base": args.base,
                          "call1": {"usage": u1, "cached_in": c1},
                          "call2": {"usage": u2, "cached_in": c2}}, indent=2))
        return 0

    print("--- raw usage, call 1 (cache write) ---")
    print(json.dumps(u1, indent=2))
    print("\n--- raw usage, call 2 (shared prefix — should read) ---")
    print(json.dumps(u2, indent=2))

    prompt_tokens = int(u2.get("prompt_tokens") or u2.get("input_tokens") or 0)
    print("\n=== verdict ===")
    if c2 is None:
        print("NO CACHE FIELD reported by this route.")
        print("The gateway returns no cached-token stat, so a discount cannot be")
        print("confirmed — and cannot be billed for correctly either. Treat the")
        print("cache assumption in _ofox's docstring as UNSUPPORTED on this route.")
    elif c2 > 0:
        pct = 100.0 * c2 / prompt_tokens if prompt_tokens else 0.0
        print(f"CACHE HIT: {c2}/{prompt_tokens} input tokens cached on call 2 ({pct:.0f}%).")
        print("The premise holds. Next: teach agent/usage.extract_usage to preserve")
        print("this field and quality/model_prices.cost to price it, or the ledger")
        print("will bill cached tokens at full rate.")
    else:
        print(f"NO HIT: 0/{prompt_tokens} input tokens cached on call 2.")
        if prompt_tokens < 1024:
            print("INCONCLUSIVE — the prefix is under the ~1024-token floor that")
            print("auto-caching usually requires. Re-run with a production-sized prefix.")
        else:
            print("The prefix is above the usual auto-cache floor, so this is a real")
            print("negative: this route does not cache our prompt. The qwen input cost")
            print("is full price every turn — re-check the total against native Gemini")
            print("before committing to the route.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
