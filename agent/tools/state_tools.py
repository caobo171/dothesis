"""LangChain tool bindings for the guarded project state.

Factory pattern (tools close over a ProjectStateStore) because the store is
per-project: the runtime builds one tool set per project/turn, while the
semantics live in agent/state.py where they're unit-tested.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from agent.state import ProjectStateStore, SliceOwnershipError


def make_state_tools(store: ProjectStateStore) -> list:
    @tool
    def read_slice(module: str) -> str:
        """Read a module's slice of the project context_store.

        Returns the module's owned keys plus its read-dependencies (per the
        slice map), the per-module status map, and the current focus. Reading
        is free: it never shifts focus or flags anything.

        Args:
            module: One of M1, M2, M3, M4, M5.
        """
        return json.dumps(store.read_slice(module), ensure_ascii=False)

    @tool
    def commit_slice(
        module: str,
        writes: dict[str, Any],
        reason: str,
        confirm_done: bool = False,
        status_overrides: dict[str, str] | None = None,
    ) -> str:
        """Write to a module's slice of the context_store. The ONLY write path.

        Deterministically: validates `writes` against the module's owned keys,
        snapshots the previous version, applies the writes, sets focus to the
        module, and flags started downstream modules `needs_review`
        (M1→M2..M5, M2→M3..M5, M3→M4,M5, M4→M5).

        Args:
            module: One of M1..M5 — the module whose slice is being written.
            writes: The slice keys to set. Must be keys the module owns.
            reason: One short sentence for the version history (shown to the user).
            confirm_done: True only on the final commit after the user confirmed
                the module's done-criteria — marks the module `done` instead of
                `in_progress`.
            status_overrides: Bootstrap only — explicit status flags for
                dependency holes (e.g. {"M2": "needs_review"}).
        """
        try:
            result = store.commit_slice(
                module, writes, reason,
                confirm_done=confirm_done,
                status_overrides=status_overrides,
            )
        except (SliceOwnershipError, ValueError) as e:
            # Surface the violation to the model so it can correct course —
            # a raise would abort the whole turn instead of one tool call.
            return json.dumps({"error": str(e)})
        return json.dumps(result, ensure_ascii=False)

    @tool
    def flag_blocker(module: str, substep: str, title: str, why: str) -> str:
        """Record a student-specific blocker under a roadmap sub-step (e.g. a
        failed discriminant-validity check). Use ONLY for a concrete obstacle
        that must be cleared before the student can proceed — not for normal
        steps. Does NOT change module status. Returns the stored task (with id).
        """
        task = store.upsert_roadmap_task(
            {"module": module, "substep": substep, "title": title, "why": why, "status": "open"})
        return json.dumps(task, ensure_ascii=False)

    @tool
    def resolve_blocker(task_id: str) -> str:
        """Mark a previously flagged blocker resolved once the student fixed it."""
        return json.dumps({"resolved": store.resolve_roadmap_task(task_id)}, ensure_ascii=False)

    return [read_slice, commit_slice, flag_blocker, resolve_blocker]
