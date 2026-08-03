"""Derived coaching roadmap for the chat UI. POST-only (project convention), authed +
ownership-checked (F0 Part B — this is a per-project read of student state).

Reads project state via DbProjectStateStore and computes the roadmap with the same
agent.roadmap functions the runtime injects each turn — one source of truth. Errs
safe: a state-load failure returns coarse module status with an empty next_action
rather than 500ing (mirrors the runtime's silent-omit state header).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import current_user, db_session
from ..models import Project, User
from agent.roadmap import (
    ROADMAP,
    SUBSTEP_LABELS,
    derive_substep,
    next_action,
    satisfied_substeps,
)
from agent.state import MODULES
from agent.timeline import timeline_status  # F11: you-are-here-vs-plan card

logger = logging.getLogger(__name__)
router = APIRouter(tags=["roadmap"])

# F5 (F0 correction): the roadmap endpoint is POLLED, so emitting
# next_action_surfaced on every call would flood PostHog. We emit ONLY when the
# surfaced action actually changes. Change-detection is a per-process in-memory
# map project_id -> (module, substep); this is deliberately NOT durable — the
# only cost of a process restart (or a second web worker) is at most one
# duplicate emit per project per restart, which is acceptable for a coaching
# signal and avoids a new DB column / coaching-key round-trip just for dedup.
_LAST_SURFACED: dict[str, tuple] = {}


def _maybe_emit_next_action(project_id: str, na: dict, user_id) -> None:
    key = (na.get("module"), na.get("substep"))
    if _LAST_SURFACED.get(project_id) == key:
        return  # unchanged since the last poll — skip to avoid a flood
    _LAST_SURFACED[project_id] = key
    from ..analytics import emit  # noqa: PLC0415 — best-effort, app layer
    emit("next_action_surfaced", str(user_id) if user_id else None,
         {"module": na.get("module"), "substep": na.get("substep"),
          "project_id": project_id})


def _authorize(db: Session, user: User, project_id: str) -> Project:
    """403 unless the caller owns the project. Kept thin so tests can stub it."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "no such project"}})
    p = db.get(Project, pid)
    if p is None or p.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "forbidden", "message": "not your project"}})
    return p


def _store_for(project_id: str):
    """Return the project's DbProjectStateStore. Isolated so tests can stub it.
    Mirrors chat_v3's construction (DbProjectStateStore(engine, project_id, workspace_dir))."""
    from ..agent_state import DbProjectStateStore
    from ..db import get_engine
    from .chat_v3 import _workspace_dir
    pid = uuid.UUID(project_id)
    return DbProjectStateStore(get_engine(), pid, _workspace_dir(pid))


def _substep_states(module: str, current: str | None, module_status: str,
                    satisfied: set[str] | None = None) -> list[dict]:
    """Render one module's spine as done / current / upcoming.

    Completion used to be purely positional (`done if i < idx`), which is only
    correct while the spine is walked in order. Mid-journey import breaks that:
    reconstruct_upstream can produce research_gaps with no literature_sources,
    so M2's current step is `familiarize` (index 0) while `find_gaps` (index 2)
    is genuinely finished. Positionally, nothing was marked done — the roadmap
    said "Find research gaps" was pending while the M2 card beside it listed
    G1 and G2.

    So an artifact-backed step that HAS its artifact is done regardless of where
    the cursor sits. Unbacked steps keep the positional rule, because position
    is the only evidence they will ever have.
    """
    spine = ROADMAP[module]
    satisfied = satisfied or set()
    idx = spine.index(current) if current in spine else (len(spine) if module_status == "done" else 0)
    out = []
    for i, sid in enumerate(spine):
        if module_status == "done":
            state = "done"
        elif sid in satisfied:
            state = "done"  # evidence beats position
        elif i < idx:
            state = "done"
        elif i == idx:
            state = "current"
        else:
            state = "upcoming"
        out.append({"id": sid, "label": SUBSTEP_LABELS.get(sid, sid), "state": state})
    return out


@router.post("/projects/{project_id}/roadmap")
async def get_roadmap(project_id: str, user: User = Depends(current_user),
                      db: Session = Depends(db_session)):
    _authorize(db, user, project_id)
    try:
        state = _store_for(project_id).load()
    except Exception:
        logger.exception("roadmap: state load failed for %s", project_id)
        state = {"focus": None, "status": {}, "contextStore": {}}

    status = state.get("status") or {}
    modules = []
    for m in MODULES:
        cur = derive_substep(m, state)
        modules.append({"id": m, "status": status.get(m, "locked"), "current": cur,
                        "substeps": _substep_states(m, cur, status.get(m, "locked"),
                                                    satisfied_substeps(m, state))})
    na = next_action(state) or {}
    # F5: emit only when the next action changed since the last poll (see above).
    _maybe_emit_next_action(project_id, na, getattr(user, "id", None))
    return {
        "modules": modules,
        "tasks": [t for t in (state.get("contextStore", {}).get("roadmap_tasks") or [])
                  if t.get("status") == "open"],
        "next_action": na,
        # F11: progress-vs-plan for the timeline card. Null-safe — {} when the
        # student has no defense date yet, so the frontend simply renders no card.
        "timeline": timeline_status(state, date.today()),
    }
