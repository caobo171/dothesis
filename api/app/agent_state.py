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

from agent.state import MODULES, SLICE_OWNERSHIP, ProjectStateStore

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

    def exists(self) -> bool:
        state = self.load()
        return bool(state["contextStore"]) or any(
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

        return {
            "status": status,
            "focus": proj.focus if proj else None,
            "contextStore": flat,
            # Version snapshots are in-turn only for now; durable history
            # lands in the version_history table in a follow-up (the agent's
            # semantics don't depend on it).
            "versionHistory": [],
        }

    def _save(self, state: dict[str, Any]) -> None:
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
