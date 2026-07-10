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

# An advisor directive names a thesis chapter; map it to the DoThesis module that
# owns that chapter's work so the raised blocker lands on the right roadmap step.
_CHAPTER_TO_MODULE = {"intro": "M5", "lit_review": "M2", "methodology": "M3",
                      "results": "M4", "discussion": "M5", "conclusion": "M5"}


def _chapter_to_module(chapter: str | None) -> str:
    return _CHAPTER_TO_MODULE.get((chapter or "").lower(), "M5")


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

    @tool
    def ingest_advisor_feedback(feedback_text: str) -> str:
        """Record a thesis supervisor's feedback. Extracts each requested change into a
        tracked directive, persists it, and raises a roadmap blocker per open item so the
        student is led to address it. Use whenever the user pastes/relays professor comments.
        """
        from agent.feedback import extract_directives  # noqa: PLC0415
        directives = extract_directives(feedback_text)
        added = 0
        for d in directives:
            stored = store.upsert_advisor_feedback(d)
            # Each open directive becomes a blocker (F2), linked by feedback_id so
            # mark_feedback_addressed can clear exactly the right one.
            store.upsert_roadmap_task({
                "module": _chapter_to_module(stored.get("chapter")),
                "substep": "", "title": f"Advisor: {stored.get('issue')}",
                "why": stored.get("required_change") or "Address this advisor comment.",
                "status": "open", "feedback_id": stored["id"]})
            added += 1
        # F5: advisor-loop signal — how many directives were captured this turn.
        from agent.analytics import emit  # noqa: PLC0415 — no-op until app wires it
        emit("advisor_feedback_ingested", None, {"count": added})
        return json.dumps({"added": added}, ensure_ascii=False)

    @tool
    def mark_feedback_addressed(feedback_id: str) -> str:
        """Mark an advisor directive addressed once the revision is done; clears its blocker."""
        ok = store.mark_advisor_feedback_addressed(feedback_id)
        for t in (store.load()["contextStore"].get("roadmap_tasks") or []):
            if t.get("feedback_id") == feedback_id:
                store.resolve_roadmap_task(t["id"])
        # When every directive is now addressed, distill recurring themes into
        # cross-project memory (F0 correction: trigger lives here). Best-effort via
        # the app-wired hook — the agent layer must not import app.user_memory.
        fb = store.load()["contextStore"].get("advisor_feedback") or []
        if fb and all(d.get("status") == "addressed" for d in fb):
            try:
                from agent.memory_hook import distill_advisor_themes  # noqa: PLC0415
                distill_advisor_themes(store, fb)
            except Exception:
                pass  # distillation is a nicety; never break the turn
        # F5: advisor-loop signal — the "addressed" side of ingested-vs-addressed.
        from agent.analytics import emit  # noqa: PLC0415 — no-op until app wires it
        emit("advisor_feedback_addressed", None, {})
        return json.dumps({"addressed": ok}, ensure_ascii=False)

    @tool
    def set_defense_date(defense_date: str) -> str:
        """Record the student's target defense/submission date (YYYY-MM-DD) and build a
        realistic backwards timeline (M1->defense) they can pace against. Reads the
        project's chosen method and planned sample size to size data collection."""
        from datetime import date  # noqa: PLC0415

        from agent.timeline import build_timeline  # noqa: PLC0415

        # Read the project's LIVE FLAT contextStore (F0 correction: the store's
        # load() returns flat keys — methodology, sample_plan — NOT the nested
        # m3_design shape the plan literal assumed; reading m3_design here would
        # always miss and silently fall back to defaults, never reaching
        # build_timeline with the real data). Mirrors make_sampling_plan_tool.
        cs = (store.load() or {}).get("contextStore") or {}
        method = cs.get("methodology") or "regression"
        target_n = (cs.get("sample_plan") or {}).get("target_n") or 200
        tl = build_timeline(date.fromisoformat(defense_date), method, target_n, date.today())
        # Persist via the dedicated coaching path — never commit_slice (a
        # calendar is not a module design decision).
        store.set_thesis_timeline(tl)
        return json.dumps(tl, ensure_ascii=False)

    return [read_slice, commit_slice, flag_blocker, resolve_blocker,
            ingest_advisor_feedback, mark_feedback_addressed, set_defense_date]
