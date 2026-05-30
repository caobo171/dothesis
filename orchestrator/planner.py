"""Artifact-DAG planner — deterministic "what to do next".

Replaces the linear `next_unconfirmed_module` walk with a dependency-aware
decision over the artifact DAG. Given the project state (and optionally a target
the user wants to reach), it returns the single next-best action:

- work        — an artifact is ready; do it
- backfill    — the target is blocked; do this ready prerequisite first
- already_done — the target is already complete
- done        — everything is complete

PURE and deterministic (an LLM is only needed elsewhere, for fuzzy redirect
classification). Additive: this module is not wired into the graph yet — the
routing swap is a separate, behaviour-changing step done under supervision.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.artifacts import ARTIFACTS, readiness

_ARTIFACT_BY_KEY = {a.key: a for a in ARTIFACTS}


def _prereq_closure(target: str) -> set[str]:
    """All transitive prerequisites of `target` (not including target itself)."""
    seen: set[str] = set()
    stack = list(_ARTIFACT_BY_KEY[target].depends_on)
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        stack.extend(_ARTIFACT_BY_KEY[k].depends_on)
    return seen


@dataclass(frozen=True)
class Decision:
    action: str               # "work" | "backfill" | "already_done" | "done"
    artifact: str | None      # the artifact to act on next (None when done)
    toward: str | None = None # the ultimate target, when action == "backfill"
    reason: str = ""


def plan_next(context_store, target: str | None = None) -> Decision:
    """Pick the next-best action over the artifact DAG.

    Without a target: work the first 'ready' artifact in DAG order, else done.
    (This reproduces the old sequential behaviour when nothing is targeted.)
    """
    status = readiness(context_store)

    if target is None:
        for art in ARTIFACTS:
            if status[art.key] == "ready":
                return Decision(action="work", artifact=art.key,
                                reason="next ready artifact")
        return Decision(action="done", artifact=None, reason="all artifacts done")

    # Targeted: the student wants to reach a specific artifact.
    if target not in _ARTIFACT_BY_KEY:
        raise KeyError(f"unknown artifact target: {target!r}")

    target_status = status[target]
    if target_status == "done":
        return Decision(action="already_done", artifact=target,
                        reason="target already complete")
    if target_status == "ready":
        return Decision(action="work", artifact=target,
                        reason="target is ready")

    # Blocked: find the deepest ready prerequisite (first in DAG order that is
    # ready) and backfill it. Iterating ARTIFACTS in order guarantees we return
    # the earliest unblocked step on the path to the target.
    closure = _prereq_closure(target)
    for art in ARTIFACTS:
        if art.key in closure and status[art.key] == "ready":
            return Decision(
                action="backfill", artifact=art.key, toward=target,
                reason=f"{target} is blocked; {art.key} is the next ready prerequisite",
            )

    # A valid DAG always has a ready ancestor for any blocked node; this is a
    # defensive fallback only.
    return Decision(action="work", artifact=target, reason="fallback")
