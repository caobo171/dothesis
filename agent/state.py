"""ProjectStateStore — the guarded `context_store` behind read_slice/commit_slice.

This is the v3 architecture's enforcement point for the v2 brief's principles
(docs/architecture/2026-06-10-deepagent-skills-architecture.md §3): the agent is
free-roaming, but state changes are deterministic code — ownership validation,
version snapshot, focus shift, downstream needs_review propagation.

Scope: the store is **per project, not per thread**. Every chat session in a
project shares one context_store; the spike backs it with a JSON file in the
project directory, and the api integration swaps the load/save pair for the
projects.context_store JSONB column without touching the semantics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULES = ["M1", "M2", "M3", "M4", "M5"]

# Which context_store keys each module may write. Mirrors the slice map in
# skills/dothesis/SKILL.md — keep the two in sync.
SLICE_OWNERSHIP: dict[str, list[str]] = {
    "M1": ["research_title", "research_questions"],
    "M2": ["literature_sources", "research_gaps"],
    "M3": ["conceptual_model", "hypotheses", "methodology", "instrument"],
    "M4": ["analysis_outline", "analysis_results"],
    "M5": ["final_sections"],
}

# Which modules each module may additionally READ (context dependencies).
READS: dict[str, list[str]] = {
    "M1": [],
    "M2": ["M1"],
    "M3": ["M1", "M2"],
    "M4": ["M3"],
    "M5": ["M1", "M2", "M3", "M4"],
}

# Mutating a module flags these downstream modules for review.
DOWNSTREAM: dict[str, list[str]] = {
    "M1": ["M2", "M3", "M4", "M5"],
    "M2": ["M3", "M4", "M5"],
    "M3": ["M4", "M5"],
    "M4": ["M5"],
    "M5": [],
}

# Keep history bounded — old snapshots beyond this are dropped oldest-first.
# 50 commits ≈ a full thesis project's worth of confirmed decisions.
VERSION_HISTORY_CAP = 50

STATE_FILENAME = "context_store.json"

# Project-scoped coaching/memory keys that live OUTSIDE the module slice map.
# Persisted by DbProjectStateStore in the `coaching` JSONB column (see
# project_db_store_persistence_gap memory). Written via dedicated store paths,
# never commit_slice — commit_slice's ownership check is module-scoped and
# would reject them.
# NOTE: field-it results are NOT here — F7 writes them into the m4_analysis
# module column (where F8 reads), so they persist via normal ownership.
COACHING_KEYS = {"roadmap_tasks", "advisor_feedback", "institution_profile",
                 "thesis_timeline"}


class SliceOwnershipError(ValueError):
    """A commit tried to write keys outside the module's owned slice."""


def _empty_state() -> dict[str, Any]:
    return {
        "status": {m: "locked" for m in MODULES},
        "focus": None,
        "contextStore": {},
        "versionHistory": [],
    }


class ProjectStateStore:
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.path = self.project_dir / STATE_FILENAME

    # -- persistence -------------------------------------------------------

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, Any]:
        if not self.exists():
            return _empty_state()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, state: dict[str, Any]) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: temp file + replace, so a crash mid-write never
        # leaves a truncated store (it's the single source of truth).
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- coaching reads ------------------------------------------------------
    # Typed getters for the COACHING_KEYS (outside the M1-M5 slice map, see
    # note above). Consumers (e.g. F3's review_thesis) must read through
    # these instead of `getattr(store, "institution_profile", ...)` — that
    # pattern reads an attribute that is never set on the store and always
    # silently returns the default, which is the bug this fixes.
    def _cs(self) -> dict:
        return self.load().get("contextStore") or {}

    def get_institution_profile(self) -> dict:
        return self._cs().get("institution_profile") or {}

    def get_advisor_feedback(self) -> list:
        return self._cs().get("advisor_feedback") or []

    def get_roadmap_tasks(self) -> list:
        return self._cs().get("roadmap_tasks") or []

    def get_thesis_timeline(self) -> dict:
        return self._cs().get("thesis_timeline") or {}

    # -- reads -------------------------------------------------------------

    def read_slice(self, module: str) -> dict[str, Any]:
        """The module's owned slice + its read-dependencies + bookkeeping.

        Reading is free: no focus shift, no flags, no version entry.
        """
        _validate_module(module)
        if not self.exists():
            return {"exists": False, "module": module}
        state = self.load()
        visible_keys: list[str] = list(SLICE_OWNERSHIP[module])
        for dep in READS[module]:
            visible_keys.extend(SLICE_OWNERSHIP[dep])
        slices = {
            k: v for k, v in state["contextStore"].items() if k in visible_keys
        }
        return {
            "exists": True,
            "module": module,
            "slices": slices,
            "status": state["status"],
            "focus": state["focus"],
        }

    # -- mutations ---------------------------------------------------------

    def _has_done_content(self, module: str, context_store: dict[str, Any]) -> bool:
        """True when `module` has produced enough to be marked done.

        Baseline: at least one of the module's owned keys is non-empty.
        M5 is special — the finished chapters can live in the m5_writing
        column (auto-draft path) rather than the owned `final_sections` key,
        so we also accept chapters when the store exposes the full view. A
        read failure there errs open (we don't block a done on a flaky read).
        """
        if any(context_store.get(k) for k in SLICE_OWNERSHIP[module]):
            return True
        if module == "M5":
            loader = getattr(self, "load_full_context_store", None)
            if loader is None:
                return False
            try:
                chapters = (loader().get("m5_writing") or {}).get("chapters") or {}
            except Exception:
                return True
            return bool(chapters)
        return False

    def commit_slice(
        self,
        module: str,
        writes: dict[str, Any],
        reason: str,
        confirm_done: bool = False,
        status_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """The ONLY write path. Validates ownership, snapshots, applies,
        shifts focus, and propagates needs_review downstream.
        """
        _validate_module(module)
        if not writes and not confirm_done and not status_overrides:
            raise ValueError("commit_slice called with nothing to do")

        illegal = sorted(set(writes) - set(SLICE_OWNERSHIP[module]))
        if illegal:
            raise SliceOwnershipError(
                f"{module} does not own {illegal}; it owns {SLICE_OWNERSHIP[module]}"
            )

        state = self.load()

        # Strict done-gate: "done" must be earned, not narrated. A module can
        # only be marked done if it has actually produced its owned output —
        # otherwise the agent could flip a module green with nothing behind it
        # (the chat-says-done / state-says-needs_review drift). We check the
        # POST-write slice so a single commit that both writes and confirms is
        # fine. Intentionally lenient (owned slice non-empty, not per-key) so
        # bootstrap imports and qualitative designs that legitimately skip some
        # keys aren't blocked. Empty-done is rejected wholesale, with a message
        # telling the agent to commit progress first.
        if confirm_done and not self._has_done_content(module, {**state["contextStore"], **writes}):
            owned = SLICE_OWNERSHIP[module]
            raise ValueError(
                f"cannot mark {module} done: its slice is empty (owns {owned}). "
                f"Commit the module's content first with confirm_done=False, "
                f"then mark it done once there is something to show."
            )

        # Snapshot BEFORE applying — history answers "what did we change away
        # from", which is what an undo/review needs.
        state["versionHistory"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "module": module,
            "reason": reason,
            "contextStore": dict(state["contextStore"]),
            "status": dict(state["status"]),
        })
        state["versionHistory"] = state["versionHistory"][-VERSION_HISTORY_CAP:]

        state["contextStore"].update(writes)
        state["focus"] = module
        state["status"][module] = "done" if confirm_done else "in_progress"

        # Flag only modules that have been started (or finished). Flagging an
        # untouched `locked` module is noise — there is nothing to re-review.
        # Bootstrap-style dependency holes are flagged explicitly via
        # status_overrides instead.
        flagged: list[str] = []
        for down in DOWNSTREAM[module]:
            if state["status"][down] != "locked":
                state["status"][down] = "needs_review"
                flagged.append(down)

        for mod, st in (status_overrides or {}).items():
            _validate_module(mod)
            state["status"][mod] = st

        self._save(state)
        return {
            "module": module,
            "focus": state["focus"],
            "status": state["status"],
            "flagged": flagged,
            "version": len(state["versionHistory"]),
        }

    # -- roadmap_tasks (coaching blockers) --------------------------------
    # Deliberately NOT commit_slice: blockers are ephemeral coaching aids, so
    # writing one must never shift focus, change module status, propagate
    # needs_review, or add a version snapshot. This keeps the module state
    # machine pristine while still funneling writes through the store.
    # roadmap_tasks is a COACHING_KEYS member, so DbProjectStateStore already
    # round-trips it (see F0 / project_db_store_persistence_gap).
    def upsert_roadmap_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Add or replace a blocker (by id). Only touches roadmap_tasks."""
        import uuid as _uuid
        state = self.load()
        tasks = list(state["contextStore"].get("roadmap_tasks") or [])
        stored = {**task}
        stored.setdefault("id", _uuid.uuid4().hex)
        stored.setdefault("status", "open")
        tasks = [t for t in tasks if t.get("id") != stored["id"]] + [stored]
        state["contextStore"]["roadmap_tasks"] = tasks
        self._save(state)
        return stored

    def resolve_roadmap_task(self, task_id: str) -> bool:
        """Flip a blocker to done. Returns False if the id wasn't found."""
        state = self.load()
        tasks = state["contextStore"].get("roadmap_tasks") or []
        hit = False
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = "done"
                hit = True
        if hit:
            self._save(state)
        return hit


def _validate_module(module: str) -> None:
    if module not in MODULES:
        raise ValueError(f"unknown module {module!r}; expected one of {MODULES}")
