"""Deterministic checks over one scenario run.

A check reads the recorded transcript (what the student would have seen, which
tools ran, the project state before and after each turn) and returns pass/fail.
Nothing here calls a model: a check that needs judgement belongs in a judge, and
judges only run after every deterministic check has had its say.

A failed check marked `critical` fails the run. A non-critical failure is
reported but does not fail it — use that for "should" behaviour that a correct
reply can legitimately skip.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from agent.runtime import _parse_options_marker

# Vietnamese function words; two hits is enough to call a reply Vietnamese.
# Same heuristic as quality/probes.py, kept local so agent/ does not import quality/.
_VI_HINTS = ("của", "và", "nghiên", "được", "trong", "này", "các", "là", "phương", "cứu")

_MISSING = object()


@dataclass
class CheckResult:
    id: str
    kind: str
    passed: bool
    critical: bool
    detail: str


def tool_ok(preview: str) -> bool:
    """Did a tool call succeed, judged from its result preview.

    Tools report expected failures as {"error": ..., "hint": ...} JSON and the
    tool guard turns crashes into error text, so absence of an error is success.
    """
    try:
        result = json.loads(preview)
    except (ValueError, TypeError):
        return bool(preview) and not re.search(r'(^|["{\s])error["\s:]', preview, re.I)
    if isinstance(result, dict):
        return not result.get("error") and result.get("ok") is not False
    return True


def lookup(state: dict, path: str) -> Any:
    """Read a dotted path such as `contextStore.m1_topic.research_title`."""
    node: Any = state
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _turns(run: dict, spec: dict) -> list[dict]:
    """The turns a check looks at: `turn: N` (0-based, -1 = last) or all."""
    turns = run["turns"]
    if "turn" in spec:
        return [turns[spec["turn"]]]
    return turns


def _names(spec: dict) -> list[str]:
    tool = spec.get("tool")
    return [tool] if isinstance(tool, str) else list(tool or [])


def _flags(spec: dict) -> int:
    return re.IGNORECASE | re.DOTALL if spec.get("ignore_case", True) else re.DOTALL


def _no_error(run: dict, spec: dict) -> tuple[bool, str]:
    errors = [e for t in _turns(run, spec) for e in t["errors"]]
    return not errors, "; ".join(errors)[:300] or "no error events"


def _tool_called(run: dict, spec: dict) -> tuple[bool, str]:
    names = _names(spec)
    calls = [c for t in _turns(run, spec) for c in t["tools"] if c["name"] in names]
    if spec.get("ok", True):
        good = [c for c in calls if c["ok"]]
        if good:
            return True, f"{good[0]['name']} succeeded"
        if calls:
            return False, f"{calls[0]['name']} failed: {calls[0]['preview'][:200]}"
        return False, f"none of {names} was called"
    return bool(calls), f"{len(calls)} call(s) to {names}"


def _tool_not_called(run: dict, spec: dict) -> tuple[bool, str]:
    names = _names(spec)
    calls = [c["name"] for t in _turns(run, spec) for c in t["tools"] if c["name"] in names]
    return not calls, f"called {calls}" if calls else f"{names} not called"


def _reply_matches(run: dict, spec: dict) -> tuple[bool, str]:
    text = "\n".join(t["reply"] for t in _turns(run, spec))
    m = re.search(spec["pattern"], text, _flags(spec))
    return bool(m), f"matched {m.group(0)!r}" if m else "pattern not found"


def _reply_not_matches(run: dict, spec: dict) -> tuple[bool, str]:
    text = "\n".join(t["reply"] for t in _turns(run, spec))
    m = re.search(spec["pattern"], text, _flags(spec))
    return not m, f"matched {m.group(0)!r}" if m else "pattern absent"


def _state_changed(run: dict, spec: dict) -> tuple[bool, str]:
    before = lookup(run["turns"][0]["state_before"], spec["path"])
    after = lookup(run["turns"][-1]["state_after"], spec["path"])
    changed = before != after and after is not _MISSING
    return changed, f"{spec['path']} {'changed' if changed else 'unchanged'}"


def _state_unchanged(run: dict, spec: dict) -> tuple[bool, str]:
    before = lookup(run["turns"][0]["state_before"], spec["path"])
    after = lookup(run["turns"][-1]["state_after"], spec["path"])
    return before == after, f"{spec['path']} {'unchanged' if before == after else 'changed'}"


def _claim_backed_by_tool(run: dict, spec: dict) -> tuple[bool, str]:
    """A reply that claims an action must come with that action succeeding.

    Checked per turn: a save claimed in turn 2 is not backed by a save in turn 1.
    """
    names = _names(spec)
    for i, t in enumerate(_turns(run, spec)):
        m = re.search(spec["claim"], t["reply"], _flags(spec))
        if not m:
            continue
        if not any(c["name"] in names and c["ok"] for c in t["tools"]):
            return False, f"turn {i} claims {m.group(0)!r} but no successful {names}"
    return True, "every claim backed (or no claim made)"


def _claim_backed_by_change(run: dict, spec: dict) -> tuple[bool, str]:
    """A reply that claims a change must leave that part of the state changed."""
    for i, t in enumerate(_turns(run, spec)):
        m = re.search(spec["claim"], t["reply"], _flags(spec))
        if not m:
            continue
        if lookup(t["state_before"], spec["path"]) == lookup(t["state_after"], spec["path"]):
            return False, f"turn {i} claims {m.group(0)!r} but {spec['path']} is unchanged"
    return True, "every claim backed (or no claim made)"


def _options_wellformed(run: dict, spec: dict) -> tuple[bool, str]:
    """An [OPTIONS] marker the UI cannot parse shows up as raw text, no buttons."""
    present = 0
    for i, t in enumerate(_turns(run, spec)):
        if "[OPTIONS" not in t["reply"]:
            continue
        present += 1
        if _parse_options_marker(t["reply"]) is None:
            return False, f"turn {i} has an [OPTIONS] marker the UI cannot parse"
    if spec.get("required") and not present:
        return False, "no [OPTIONS] marker"
    return True, f"{present} well-formed marker(s)"


def _language(run: dict, spec: dict) -> tuple[bool, str]:
    if spec.get("value") != "vi":
        raise ValueError(f"unsupported language {spec.get('value')!r}")
    for i, t in enumerate(_turns(run, spec)):
        low = t["reply"].lower()
        if sum(1 for h in _VI_HINTS if h in low) < 2:
            return False, f"turn {i} reply does not read as Vietnamese"
    return True, "Vietnamese"


def _max_tool_calls(run: dict, spec: dict) -> tuple[bool, str]:
    n = sum(len(t["tools"]) for t in _turns(run, spec))
    return n <= spec["max"], f"{n} tool call(s), max {spec['max']}"


CHECKS: dict[str, Callable[[dict, dict], tuple[bool, str]]] = {
    "no_error": _no_error,
    "tool_called": _tool_called,
    "tool_not_called": _tool_not_called,
    "reply_matches": _reply_matches,
    "reply_not_matches": _reply_not_matches,
    "state_changed": _state_changed,
    "state_unchanged": _state_unchanged,
    "claim_backed_by_tool": _claim_backed_by_tool,
    "claim_backed_by_change": _claim_backed_by_change,
    "options_wellformed": _options_wellformed,
    "language": _language,
    "max_tool_calls": _max_tool_calls,
}


def run_checks(run: dict, specs: list[dict]) -> list[CheckResult]:
    results = []
    for i, spec in enumerate(specs):
        kind = spec["kind"]
        fn = CHECKS.get(kind)
        if fn is None:
            raise ValueError(f"unknown check kind {kind!r}")
        passed, detail = fn(run, spec)
        results.append(CheckResult(
            id=spec.get("id") or f"{kind}#{i}",
            kind=kind,
            passed=passed,
            critical=spec.get("critical", True),
            detail=detail,
        ))
    return results
