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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from agent.state import (
    COACHING_KEYS,
    MODULES,
    NON_CONTENT_KEYS,
    SLICE_OWNERSHIP,
    ProjectStateStore,
    strip_reconstruction_meta,
)

from .models import ContextStore as DbContextStore
from .models import Project

logger = logging.getLogger(__name__)

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

    def commit_reconstructed(
        self,
        module: str,
        slice_: dict[str, Any],
        reason: str = "reconstructed from existing work",
    ) -> dict[str, Any]:
        """Same contract as the base store, plus the fields commit_slice can't carry.

        A reconstructed slice is a whole M-output (M2 also infers
        `research_state_summary` and `theoretical_framework`; M3 infers
        `paradigm` / `design` / `tool` / `sampling_strategy` /
        `target_sample_size`), but SLICE_OWNERSHIP is deliberately narrower than
        the schema — commit_slice would reject those keys as unowned, and
        load/_save only round-trip owned keys. So they are merged straight into
        the module's JSONB column here, BEFORE the commit_slice below: _save
        merges over the existing column rather than rebuilding it, so the
        commit preserves them (project_db_store_persistence_gap).
        """
        clean = strip_reconstruction_meta(slice_)
        extra = {k: v for k, v in clean.items() if k not in SLICE_OWNERSHIP[module]}
        column = _MODULE_COLUMN.get(module)
        if extra and column:
            with self.engine.connect() as conn:
                row = conn.execute(
                    select(DbContextStore.__table__)
                    .where(DbContextStore.__table__.c.project_id == self.project_id)
                ).first()
                # `_source` marks the provenance of this slice for anything that
                # needs to tell inferred state from state the student authored.
                merged = {**(getattr(row, column, None) or {}), **extra,
                          "_source": "reconstructed"}
                if row is None:
                    conn.execute(DbContextStore.__table__.insert().values(
                        project_id=self.project_id, **{column: merged}))
                else:
                    conn.execute(
                        DbContextStore.__table__.update()
                        .where(DbContextStore.__table__.c.project_id == self.project_id)
                        .values(**{column: merged})
                    )
                conn.commit()
        return super().commit_reconstructed(module, clean, reason=reason)

    def exists(self) -> bool:
        state = self.load()
        # Coaching keys (e.g. an F4 institution_default seed) must NOT count
        # as "the project has started" — only actual module-slice content
        # should, or onboarding treats every fresh project as in-progress.
        # NON_CONTENT_KEYS are excluded for the same reason from the other side:
        # they ARE module-slice keys (so the stores persist them), but an audit
        # row is bookkeeping about the work, never the work itself.
        module_keys = set(state["contextStore"]) - COACHING_KEYS - NON_CONTENT_KEYS
        return bool(module_keys) or any(
            s != "locked" for s in state["status"].values()
        )

    # --- Humanize style anchor -------------------------------------------
    #
    # Exposed on the STORE, duck-typed like persist_export_artifacts, because
    # the caller is agent/tools/writing.py and `agent -> api.app` is the banned
    # import direction. The store is the seam that already crosses it.
    #
    # Anchored on the USER, not the project: a student's writing voice is the
    # same across theses, and asking for 150 words once per project instead of
    # once per student is the difference between a feature people use and one
    # they avoid. The owner is resolved from project_id since the store is not
    # owner-aware.

    def _owner_id(self) -> uuid.UUID | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(Project.__table__.c.user_id)
                .where(Project.__table__.c.id == self.project_id)
            ).first()
        return row[0] if row else None

    def load_writing_anchor(self) -> str | None:
        """The student's stored ~150-word writing sample, if they've given one."""
        from .db import get_session_factory  # noqa: PLC0415 — avoid import cycle
        from .user_memory import load_user_prefs  # noqa: PLC0415
        uid = self._owner_id()
        if uid is None:
            return None
        try:
            with get_session_factory()() as db:
                anchor = (load_user_prefs(db, uid) or {}).get("writing_anchor")
            return anchor if isinstance(anchor, str) and anchor.strip() else None
        except Exception:  # noqa: BLE001
            logger.exception("load_writing_anchor failed for project %s", self.project_id)
            return None

    def save_writing_anchor(self, anchor: str) -> None:
        """Remember the sample so humanize never has to ask this student again.

        Best-effort: a failure here must not fail the humanize turn the student
        actually asked for — they still get their rewrite, they just get asked
        again next time.
        """
        from .db import get_session_factory  # noqa: PLC0415
        from .user_memory import write_user_prefs  # noqa: PLC0415
        uid = self._owner_id()
        if uid is None or not anchor.strip():
            return
        try:
            with get_session_factory()() as db:
                write_user_prefs(db, uid, {"writing_anchor": anchor.strip()})
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("save_writing_anchor failed for project %s", self.project_id)

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

    @staticmethod
    def _missing_chapters(sections: list[dict]) -> list[str]:
        """Canonical chapters absent from `sections`. Empty ⇒ a whole thesis.

        Matches on chapter_name first and falls back to the title maps, because
        sections_from_m5_slice emits {title, prose} for the `chapters` shape and
        preserved imports carry chapter_name. Fail-open: on any import or shape
        problem this reports nothing missing, so a bug here can only restore the
        old behaviour, never block a legitimate export.
        """
        try:
            from orchestrator.tools.m5_writing import (  # noqa: PLC0415
                M5_CHAPTER_ORDER, M5_CHAPTER_TITLES, M5_CHAPTER_TITLES_VI,
            )
            have_names = {(s.get("chapter_name") or "") for s in sections if isinstance(s, dict)}
            have_titles = {(s.get("title") or "").strip().lower()
                           for s in sections if isinstance(s, dict)}
            missing = []
            for name in M5_CHAPTER_ORDER:
                if name in have_names:
                    continue
                titles = {(M5_CHAPTER_TITLES.get(name) or "").strip().lower(),
                          (M5_CHAPTER_TITLES_VI.get(name) or "").strip().lower()}
                if titles & have_titles:
                    continue
                missing.append(name)
            return missing
        except Exception:
            return []

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
                # Only export a WHOLE thesis. This hook renders exactly what
                # final_sections holds — it cannot compose, and must not: it
                # runs inside a store commit, where an LLM call has no business.
                #
                # That was harmless while final_sections was empty until the
                # composer filled it. Once the import began preserving the
                # student's chapters 4 and 5, this fired with two chapters in
                # hand and shipped a 35KB "full thesis" with no introduction,
                # literature review or methodology — and because the export came
                # from here rather than the export_docx tool, the chat had no
                # download card either, so the reply just said the files were
                # somewhere in the Context store.
                #
                # Skipping is the safe half: the `done` flag and the "no export
                # yet" hint both stand, and export_docx (which CAN compose, and
                # refuses a partial with incomplete_export) still produces the
                # real document when the user or the agent asks for it.
                missing = self._missing_chapters(sections)
                if missing:
                    log.warning(
                        "M5 auto-export skipped for %s — draft has only %d "
                        "chapter(s), missing %s. Leaving the export to "
                        "export_docx, which can compose them.",
                        self.project_id, len(sections), missing,
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
