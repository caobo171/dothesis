"""Behavioral probes for DoThesis's model requirements — markers, instruction-following,
language. Deterministic scoring where possible; the runner adds a judge for fluency.

These are the fast, decisive signals a per-token price ignores: does the model emit our
[OPTIONS]/{{cite}} markers, follow terse/JSON instructions, and answer in Vietnamese?
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# A few high-signal Vietnamese function words for a cheap language check (no heavy dep).
_VI_HINTS = ("của", "và", "nghiên", "được", "trong", "này", "các", "là", "phương", "cứu")


def score_probe(completion: str, expect: dict) -> bool:
    """Deterministically score one completion against an expectation.

    kinds: marker (a bracketed marker like [OPTIONS] is present), regex (pattern
    matches — used for {{cite}} and terseness), json (parses as a JSON object),
    language (Vietnamese heuristic)."""
    kind = expect.get("kind")
    val = expect.get("value")
    text = completion or ""
    if kind == "marker":
        # F0 fix: the plan's marker branch was deliberately convoluted; the
        # intent is simply "is the [VAL] marker present". {{cite}} is checked via
        # a `regex` probe, not here.
        return f"[{val}]" in text
    if kind == "regex":
        return re.search(val, text) is not None
    if kind == "json":
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e == -1:
            return False
        try:
            json.loads(text[s:e + 1])
            return True
        except Exception:
            return False
    if kind == "language" and val == "vi":
        low = text.lower()
        return sum(1 for h in _VI_HINTS if h in low) >= 2
    return False


def load_probes(directory: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.json"))]
