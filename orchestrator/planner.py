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

    # Targeted planning is added in the next task.
    raise NotImplementedError
