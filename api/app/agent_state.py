"""DB-backed ProjectStateStore for the v3 deep agent.

Maps the agent's flat state shape (research_title, research_gaps, …) onto the
EXISTING rows the rest of the app already reads — context_store slice columns
(m1_topic…m5_writing), projects.module_status, projects.focus — so the web's
module tracker, dashboard cards, and ContextPanel keep working unchanged while
the agent drives.

Threading: tool calls run on LangGraph executor threads, not the request's
asyncio loop, so this store takes the *engine* (thread-safe) and opens a
short-lived connection per load/save instead of sharing the request Session.

The context_store stays PROJECT-scoped (shared by all threads/sessions of a
project) — the user's invariant; thread-scoping lives only in the
conversation checkpointer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from agent.state import COACHING_KEYS, MODULES, SLICE_OWNERSHIP, ProjectStateStore

from .models import ContextStore as DbContextStore
from .models import Project

_MODULE_COLUMN = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


class DbProjectStateStore(ProjectStateStore):
    def __init__(self, engine, project_id: uuid.UUID, workspace_dir):
        # workspace_dir only anchors uploads/exports; state lives in the DB.
        super().__init__(workspace_dir)
        self.engine = engine
        self.project_id = project_id

    def commit_slice(
        self,
        module: str,
        writes: dict[str, Any],
        reason: str,
        confirm_done: bool = False,
        status_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Instrumented write path: emit agent-quality events around the base
        commit_slice. Decision (F5 Task 2): this is where user/project ids are
        known and every module-status transition funnels through, so it's the
        single chokepoint for the completion-funnel and gate-rate signal.

        Best-effort throughout — `emit` swallows its own errors, and we never let
        analytics change the commit's outcome (the ValueError is always re-raised).
        """
        from .analytics import emit  # noqa: PLC0415 — local import keeps the state layer inert-importable
        # The store isn't (yet) owner-aware; pass None rather than fabricate an
        # id. emit tolerates None (distinct_id -> "anonymous").
        uid = getattr(self, "user_id", None)
        before = self.load()["status"].get(module)
        try:
            result = super().commit_slice(
                module, writes, reason,
                confirm_done=confirm_done, status_overrides=status_overrides,
            )
        except ValueError as e:
            # The strict empty-done gate ("cannot mark <M> done: its slice is
            # empty") is the hallucinated-completion catch — record it, then
            # re-raise so the caller behaviour is unchanged. Other ValueErrors
            # (ownership, nothing-to-do) are not gate rejections, so we skip them.
            if "cannot mark" in str(e):
                emit("done_rejected_empty", uid,
                     {"module": module, "project_id": str(self.project_id)})
            raise
        after = self.load()["status"].get(module)
        if after != before:
            emit("module_status_changed", uid,
                 {"module": module, "from": before, "to": after,
                  "project_id": str(self.project_id)})
        # `flagged` = downstream modules this commit knocked to needs_review — the
        # raw signal for "a late upstream edit invalidated finished work".
        flagged = result.get("flagged", []) if isinstance(result, dict) else []
        if flagged:
            emit("needs_review_propagated", uid,
                 {"module": module, "downstream": flagged,
                  "project_id": str(self.project_id)})
        return result

    def exists(self) -> bool:
        state = self.load()
        # Coaching keys (e.g. an F4 institution_default seed) must NOT count
        # as "the project has started" — only actual module-slice content
        # should, or onboarding treats every fresh project as in-progress.
        module_keys = set(state["contextStore"]) - COACHING_KEYS
        return bool(module_keys) or any(
            s != "locked" for s in state["status"].values()
        )

    def load(self) -> dict[str, Any]:
        with self.engine.connect() as conn:
            proj = conn.execute(
                select(Project.__table__.c.focus, Project.__table__.c.module_status)
                .where(Project.__table__.c.id == self.project_id)
            ).first()
            cs = conn.execute(
                select(DbContextStore.__table__)
                .where(DbContextStore.__table__.c.project_id == self.project_id)
            ).first()

        status = {m: "locked" for m in MODULES}
        if proj and proj.module_status:
            status.update({k: v for k, v in proj.module_status.items() if k in status})

        flat: dict[str, Any] = {}
        if cs:
            for module, column in _MODULE_COLUMN.items():
                slice_dict = getattr(cs, column, None) or {}
                # Only lift the keys the v3 shape owns — legacy graph_v2
                # bookkeeping (confirmed_at, phase markers, _awaiting_field)
                # stays in the column but out of the agent's view.
                for key in SLICE_OWNERSHIP[module]:
                    if key in slice_dict:
                        flat[key] = slice_dict[key]
            # Coaching keys live in their own column, outside the module
            # slice map entirely — lift them the same way so the agent sees
            # one flat contextStore regardless of which column backs a key.
            if getattr(cs, "coaching", None):
                for key, value in cs.coaching.items():
                    if key in COACHING_KEYS:
                        flat[key] = value

        return {
            "status": status,
            "focus": proj.focus if proj else None,
            "contextStore": flat,
            # Version snapshots are in-turn only for now; durable history
            # lands in the version_history table in a follow-up (the agent's
            # semantics don't depend on it).
            "versionHistory": [],
        }

    def load_full_context_store(self) -> dict[str, Any]:
        """Nested {m1_topic: {...}, m2_literature: {...}, …} for callers that
        need WHOLE module slices (e.g. the engine chapter composers), not the
        flattened owned-keys view `load()` returns.
        """
        with self.engine.connect() as conn:
            cs = conn.execute(
                select(DbContextStore.__table__)
                .where(DbContextStore.__table__.c.project_id == self.project_id)
            ).first()
        out: dict[str, Any] = {}
        if cs:
            for _module, column in _MODULE_COLUMN.items():
                out[column] = getattr(cs, column, None) or {}
        return out

    def _save(self, state: dict[str, Any]) -> None:
        # Capture the PRE-save M5 status so the post-save auto-export hook
        # can detect the locked/in_progress → done transition. Without this
        # we'd re-export on every commit while M5 is already done.
        prev_state = self.load()
        prev_m5_status = prev_state["status"].get("M5")
        flat = state["contextStore"]
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.connect() as conn:
            # Build each module's slice column from its owned flat keys,
            # merging over the existing column so legacy keys survive.
            existing = conn.execute(
                select(DbContextStore.__table__)
                .where(DbContextStore.__table__.c.project_id == self.project_id)
            ).first()
            values: dict[str, Any] = {}
            for module, column in _MODULE_COLUMN.items():
                current = dict(getattr(existing, column, None) or {}) if existing else {}
                touched = False
                for key in SLICE_OWNERSHIP[module]:
                    if key in flat:
                        current[key] = flat[key]
                        touched = True
                # confirmed_at is the legacy "done" marker ContextPanel falls
                # back on — keep it in sync with the status map.
                if state["status"].get(module) == "done" and not current.get("confirmed_at"):
                    current["confirmed_at"] = now
                    touched = True
                if touched or current:
                    values[column] = current or None
            # Coaching keys get their own merge-over-existing pass — MERGE,
            # never rebuild, same reasoning as the per-module columns above:
            # a rebuild from `flat` alone would wipe any coaching key not
            # touched by THIS save (e.g. saving roadmap_tasks would otherwise
            # blow away a previously-saved institution_profile).
            existing_coaching = dict(getattr(existing, "coaching", None) or {}) if existing else {}
            for key in COACHING_KEYS:
                if key in flat:
                    existing_coaching[key] = flat[key]
            if existing_coaching:
                values["coaching"] = existing_coaching
            if existing is None:
                conn.execute(DbContextStore.__table__.insert().values(
                    project_id=self.project_id, **values))
            elif values:
                conn.execute(
                    DbContextStore.__table__.update()
                    .where(DbContextStore.__table__.c.project_id == self.project_id)
                    .values(**values)
                )
            conn.execute(
                Project.__table__.update()
                .where(Project.__table__.c.id == self.project_id)
                .values(focus=state["focus"], module_status=state["status"])
            )
            conn.commit()

        # M5 auto-export: a docx + pdf are part of the M5 done-criteria,
        # not a separate user-triggered step. When this commit flipped M5
        # to `done`, run the exporter in-line and write the artifacts back
        # so the ContextPanel can show download links the moment the user
        # sees the status flip.
        if (
            prev_m5_status != "done"
            and state["status"].get("M5") == "done"
        ):
            self._auto_export_m5()

    def _auto_export_m5(self) -> None:
        """Run the engine docx/pdf pipeline and persist artifacts.

        Idempotent + best-effort: a failure here must NOT raise, because the
        slice commit that triggered it has already been written to the DB.
        Raising would mean the user sees an error AFTER their M5 commit
        succeeded — confusing. Instead we log and the user can re-export
        via POST /projects/{pid}/m5/export.
        """
        import logging
        log = logging.getLogger(__name__)
        try:
            # Lazy import: keep the engine renderer out of the cold-import
            # path of every project that's nowhere near M5.
            from orchestrator.tools.m5_writing import (
                run_export,
                sections_from_m5_slice,
            )
            from .models import ContextStore as DbContextStore
            from sqlalchemy.orm import Session

            with Session(self.engine) as db:
                cs = db.get(DbContextStore, self.project_id)
                if cs is None:
                    log.warning("M5 auto-export: no context_store row for %s", self.project_id)
                    return
                sections = sections_from_m5_slice(cs.m5_writing or {})
                references = (cs.m2_literature or {}).get("literature_sources") or []
                language = (cs.m1_topic or {}).get("language") or "vi"
                if not sections:
                    # M5 done was claimed without usable chapter prose (neither
                    # the chapters shape nor final_sections carried text). The
                    # user keeps the `done` flag but no export; the ContextPanel
                    # shows the "no export yet" hint.
                    log.warning(
                        "M5 auto-export skipped for %s — no drafted prose in "
                        "chapters or final_sections.", self.project_id,
                    )
                    return

            artifacts = run_export(sections, str(self.project_id), references=references, language=language)
            self.persist_export_artifacts(artifacts)
            # F5: auto surface (headless M5 done-hook) export completed. Emitted
            # here rather than in job_runner because this IS the auto-mode export
            # chokepoint; best-effort, no user id at the store layer.
            from .analytics import emit  # noqa: PLC0415
            emit("export_completed", getattr(self, "user_id", None),
                 {"scope": "full", "surface": "auto", "project_id": str(self.project_id)})
            log.info("M5 auto-export completed for project %s", self.project_id)
        except Exception:
            log.exception("M5 auto-export failed for project %s", self.project_id)

    def persist_export_artifacts(self, artifacts: list[dict], scope: str = "full") -> None:
        """Record export artifacts as rows in the `exports` table, tagged with
        `scope` ("full" thesis, or "M1".."M4" for a single-module export).

        Exports are module-agnostic now — they no longer live inside
        m5_writing.export_artifacts (which made a per-module export show up under
        M5). The ContextPanel reads the dedicated /exports/list endpoint and the
        download route authorizes against these rows. Shared by the M5
        auto-export hook (scope=full) and the agent's export_docx tool. Uses a
        fresh ORM Session (tool calls run on executor threads).
        """
        import uuid as _uuid

        from sqlalchemy.orm import Session

        from .models import Export as DbExport

        with Session(self.engine) as db:
            for a in artifacts or []:
                s3_key = a.get("s3_key")
                if not s3_key:
                    continue
                db.add(DbExport(
                    id=_uuid.uuid4(),
                    project_id=self.project_id,
                    scope=scope,
                    kind=a.get("kind") or "docx",
                    s3_key=s3_key,
                    filename=s3_key.rsplit("/", 1)[-1],
                    size_bytes=int(a.get("size_bytes") or 0),
                ))
            db.commit()
