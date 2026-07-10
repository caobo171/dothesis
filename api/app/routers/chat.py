"""Chat router — project + thread CRUD + streaming message endpoint.

Mounted under /api/v1 by main.py only when ORCHESTRATOR_ENABLED=true.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import db_session, get_session_factory
from ..deps import current_user
from ..models import ContextStore, Message, Project, Thread, User

router = APIRouter(tags=["chat"])


# ----------------------------------------------------------------------------
# Request / response models
# ----------------------------------------------------------------------------

class CreateProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    field: str | None = None
    language: str = "en"
    citation_style: str = "apa"


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    field: str | None
    language: str
    citation_style: str
    status: str
    current_module: str
    # Brief §1.4 — conversation focus (distinct from current_module). Nullable
    # during the dual-write window of PR #1/#2: clients can fall back to
    # current_module when focus is None.
    focus: str | None = None
    # Brief §1.4 — per-module workflow status (locked|in_progress|done|needs_review).
    # JSONB Dict[ModuleId, str]; '{}' until the first orchestrator turn writes
    # the computed status back via compute_status_map.
    module_status: dict = Field(default_factory=dict)
    context_store: dict
    created_at: Any
    updated_at: Any


class ImportBody(BaseModel):
    """Seed existing work into a project. `slices` maps context_store field names
    (m1_topic, m2_literature, m3_design, m4_analysis, m5_writing) to their content;
    unknown keys are ignored by merge_import."""
    slices: dict[str, dict] = Field(default_factory=dict)


class AssessBody(BaseModel):
    """Free-form existing work to classify into proposed slices."""
    text: str = Field(..., min_length=1)


class CreateThreadBody(BaseModel):
    name: str = Field(default="New thread", min_length=1, max_length=200)


class ThreadOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    langgraph_thread_id: str
    created_at: Any
    last_active_at: Any


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404,
                            detail={"error": {"code": "not_found", "message": "project not found"}})
    return p


def _orch_context_store(db: Session, project_id: uuid.UUID):
    """Build an orchestrator ContextStore from the project's DB row.

    Single chokepoint reused by the artifact/import endpoints (and mirrors the
    seed the chat router builds for the first graph turn).
    """
    from orchestrator.state import ContextStore as OrchestratorContextStore
    cs = db.get(ContextStore, project_id)
    return OrchestratorContextStore(
        m1_topic=(cs.m1_topic if cs else None),
        m2_literature=(cs.m2_literature if cs else None),
        m3_design=(cs.m3_design if cs else None),
        m4_analysis=(cs.m4_analysis if cs else None),
        m5_writing=(cs.m5_writing if cs else None),
    )


# Sentinel so list_projects can pass a pre-fetched ContextStore (including a
# legitimate None for projects that have no row yet) without _serialize_project
# falling back to a per-row db.get — that fallback is what caused the N+1.
_CS_UNSET: Any = object()


def _serialize_project(db: Session, p: Project, cs: Any = _CS_UNSET) -> ProjectOut:
    # Single-project callers omit `cs` and we look it up here; the list endpoint
    # passes the row it already batch-loaded so we never query per project.
    if cs is _CS_UNSET:
        cs = db.get(ContextStore, p.id)
    return ProjectOut(
        id=p.id, name=p.name, field=p.field, language=p.language,
        citation_style=p.citation_style, status=p.status,
        current_module=p.current_module,
        # PR #1/#2 — surface the new focus + module_status columns. focus
        # falls back to current_module on the client side when None during
        # the dual-write window; module_status defaults to {} until the
        # first orchestrator turn populates it.
        focus=p.focus,
        module_status=p.module_status or {},
        context_store={
            "m1_topic":      cs.m1_topic      if cs else None,
            "m2_literature": cs.m2_literature if cs else None,
            "m3_design":     cs.m3_design     if cs else None,
            "m4_analysis":   cs.m4_analysis   if cs else None,
            "m5_writing":    cs.m5_writing    if cs else None,
        },
        created_at=p.created_at, updated_at=p.updated_at,
    )


# ----------------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------------

@router.post("/projects", response_model=ProjectOut)
def create_project(body: CreateProjectBody,
                   user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    p = Project(user_id=user.id, name=body.name, field=body.field,
                language=body.language, citation_style=body.citation_style,
                current_module="M1", status="draft")
    db.add(p); db.flush()
    db.add(Thread(project_id=p.id, name="Main",
                  langgraph_thread_id=str(uuid.uuid4())))
    db.add(ContextStore(project_id=p.id))
    # Cross-project memory (Phase 0): remember the setup choices as this user's
    # defaults so the next /new form pre-fills. Preferences only — never content.
    try:
        from ..user_memory import write_user_prefs
        write_user_prefs(db, user.id, {
            "field": body.field,
            "language": body.language,
            "citation_style": body.citation_style,
        }, source_project_id=p.id)
    except Exception:  # noqa: BLE001 — memory is best-effort, never block create
        import logging
        logging.getLogger(__name__).exception("user_memory capture failed")
    db.commit(); db.refresh(p)
    # F4: if the user has an institution_default (learned from a prior project),
    # seed this project's institution_profile so it starts pre-warned. Post-commit
    # so the ContextStore row is visible to the store's own connection. Best-effort.
    try:
        from ..user_memory import load_user_prefs
        inst = load_user_prefs(db, user.id).get("institution_default")
        if isinstance(inst, dict) and inst:
            from ..agent_state import DbProjectStateStore
            from .chat_v3 import _workspace_dir
            DbProjectStateStore(db.bind, p.id, _workspace_dir(p.id)).set_institution_profile(inst)
    except Exception:  # noqa: BLE001 — seeding is best-effort, never block create
        import logging
        logging.getLogger(__name__).exception("institution_default seeding failed")
    return _serialize_project(db, p)


@router.post("/me/prefs")
def get_user_prefs(user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    """Return this user's remembered preferences for pre-filling the /new form.

    Cross-project memory (Phase 0). Empty {} for a first-time user. Preferences
    only (language/citation_style/research_approach/field) — never thesis content.
    """
    from ..user_memory import load_user_prefs
    return load_user_prefs(db, user.id)


# Renamed from GET /projects → POST /projects/list: POST /projects already
# creates a project, so the list read needs a distinct path. Token rides in the
# JSON body (read by current_user), never the URL.
@router.post("/projects/list", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    """Return the current user's projects, most recently updated first.

    Decision: same serializer as the single-project GET so the frontend's
    ProjectListGrid + project-detail page share one Project type. Ordered by
    updated_at desc so the project the user just edited (or just created)
    appears at the top — without this the list felt non-deterministic and the
    user couldn't tell whether their just-created project landed at all.
    """
    projects = (db.query(Project)
                  .filter_by(user_id=user.id)
                  .order_by(Project.updated_at.desc())
                  .all())
    # Batch-load every project's ContextStore in ONE query instead of a per-row
    # db.get (the previous N+1: 1 + len(projects) queries, each pulling full
    # m1–m5 JSONB). Map by project_id and hand each row to the serializer.
    cs_by_id: dict[uuid.UUID, ContextStore] = {}
    if projects:
        ids = [p.id for p in projects]
        cs_rows = db.query(ContextStore).filter(ContextStore.project_id.in_(ids)).all()
        cs_by_id = {cs.project_id: cs for cs in cs_rows}
    return [_serialize_project(db, p, cs_by_id.get(p.id)) for p in projects]


@router.post("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    return _serialize_project(db, p)


@router.post("/projects/{project_id}/artifacts")
def get_artifacts(project_id: uuid.UUID,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)) -> dict[str, str]:
    """Readiness map for every thesis artifact: done / ready / blocked.

    Powers the "enter at any step" UI — the frontend can show which deliverables
    are finished, which are ready to start now, and which are still blocked by
    unmet prerequisites. Computed from the artifact dependency DAG
    (orchestrator/artifacts.py) over the project's persisted context_store.
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import readiness
    return readiness(_orch_context_store(db, project_id))


@router.post("/projects/{project_id}/impact/{artifact}")
def get_impact(project_id: uuid.UUID, artifact: str,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> dict[str, list[str]]:
    """Blast radius of editing `artifact`: which downstream slices depend on
    it (full closure) and which DONE ones may need a re-review (stale).

    Powers the 'editing this step invalidates these later steps' UX. Backed
    by orchestrator.artifacts.{dependents_closure, stale_after_change} —
    the API is just authn + serialization on top of the existing DAG.
    422 for unknown artifact keys keeps the error shape consistent with
    /reconstruct/{artifact}.
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import (
        _ARTIFACT_BY_KEY, dependents_closure, stale_after_change,
    )
    if artifact not in _ARTIFACT_BY_KEY:
        from fastapi import HTTPException
        raise HTTPException(status_code=422,
                            detail=f"unknown artifact: {artifact}")
    cs = _orch_context_store(db, project_id)
    # Sort both lists by the DAG order baked into ARTIFACTS so the frontend
    # gets a stable, top-down sequence — easier to reason about than a set.
    from orchestrator.artifacts import ARTIFACTS
    closure = dependents_closure(artifact)
    ordered_deps = [a.key for a in ARTIFACTS if a.key in closure]
    return {
        "dependents": ordered_deps,
        "stale": stale_after_change(cs, artifact),
    }


@router.post("/projects/{project_id}/import")
def import_work(project_id: uuid.UUID, body: ImportBody,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)) -> dict[str, str]:
    """Seed the project's context_store from a student's existing work, then
    return the updated readiness map.

    The first half of "enter at any step": drop in a topic + a methodology and
    the system records them (tagged _source=imported) and tells you what's now
    ready vs still blocked. (The planner that ROUTES to a chosen step + backfills
    missing prerequisites lands in a later phase.)
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import readiness
    from orchestrator.intake import merge_import

    merged = merge_import(_orch_context_store(db, project_id), body.slices)
    cs = db.get(ContextStore, project_id)
    if cs is None:
        cs = ContextStore(project_id=project_id)
        db.add(cs)
    # Reassign (new dicts) so SQLAlchemy persists the JSONB columns.
    cs.m1_topic = merged.m1_topic
    cs.m2_literature = merged.m2_literature
    cs.m3_design = merged.m3_design
    cs.m4_analysis = merged.m4_analysis
    cs.m5_writing = merged.m5_writing
    db.commit()
    return readiness(merged)


@router.post("/projects/{project_id}/assess")
def assess(project_id: uuid.UUID, body: AssessBody,
           user: User = Depends(current_user),
           db: Session = Depends(db_session)) -> dict:
    """Classify pasted existing work into PROPOSED artifact slices (dry-run).

    Returns the detected slices plus the readiness map *if* they were applied —
    so the UI can show "we found a topic + a methodology; import these?" The
    student reviews/edits, then POSTs /import to actually commit. Nothing is
    persisted here (never silently seed assessed work).
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import readiness
    from orchestrator.intake import assess_work, merge_import

    detected = assess_work(body.text)
    preview = merge_import(_orch_context_store(db, project_id), detected)
    return {"detected": detected, "readiness_if_applied": readiness(preview)}


@router.post("/projects/{project_id}/reconstruct/{artifact}")
def reconstruct(project_id: uuid.UUID, artifact: str,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)) -> dict:
    """Propose a reconstructed slice for a SKIPPED prerequisite (dry-run).

    Infers `artifact` from the student's existing work and returns the candidate,
    whether it clears the gate to confirm, and which fields to review. For
    `design` the gate is the lighter STRUCTURAL one (the Phase-3 eval showed the
    detail artifacts can't be inferred and shouldn't block); other artifacts use
    their full DoD. Never auto-committed — the student confirms, then /import.
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import _ARTIFACT_BY_KEY, dod_design_structural
    from orchestrator.backfill import reconstruct_artifact
    if artifact not in _ARTIFACT_BY_KEY:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "unknown_artifact",
                              "message": f"unknown artifact: {artifact}"}},
        )
    candidate = reconstruct_artifact(artifact, _orch_context_store(db, project_id))
    gate = {"design": dod_design_structural}.get(
        artifact, _ARTIFACT_BY_KEY[artifact].dod)
    result = gate(candidate)
    return {"artifact": artifact, "candidate": candidate,
            "ready_to_confirm": result.done, "review": result.gaps}


# ----------------------------------------------------------------------------
# Threads
# ----------------------------------------------------------------------------

# Renamed from GET → POST .../threads/list: POST .../threads already creates a
# thread, so the list read needs a distinct path.
@router.post("/projects/{project_id}/threads/list", response_model=list[ThreadOut])
def list_threads(project_id: uuid.UUID,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    _owned_project(db, user, project_id)
    return db.query(Thread).filter_by(project_id=project_id).order_by(Thread.created_at).all()


@router.post("/projects/{project_id}/threads", response_model=ThreadOut)
def create_thread(project_id: uuid.UUID, body: CreateThreadBody,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    _owned_project(db, user, project_id)
    t = Thread(project_id=project_id, name=body.name,
               langgraph_thread_id=str(uuid.uuid4()), status="active")
    db.add(t); db.commit(); db.refresh(t)
    return t


@router.post("/projects/{project_id}/threads/start-at/{artifact}",
             response_model=ThreadOut)
def start_at(project_id: uuid.UUID, artifact: str,
             user: User = Depends(current_user),
             db: Session = Depends(db_session)):
    """Open a thread that targets a specific artifact (enter-at-any-step).

    The planner routes toward `artifact` on the first turn — backfilling any
    missing prerequisites and skipping unneeded modules. `artifact` must be a
    known artifact key (topic, literature, design, analysis, ch_*).
    """
    _owned_project(db, user, project_id)
    from orchestrator.artifacts import ARTIFACTS
    if artifact not in {a.key for a in ARTIFACTS}:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "unknown_artifact",
                              "message": f"unknown artifact: {artifact}"}},
        )
    t = Thread(project_id=project_id, name=f"Start at {artifact}",
               langgraph_thread_id=str(uuid.uuid4()), status="active",
               target_artifact=artifact)
    db.add(t); db.commit(); db.refresh(t)
    return t


@router.post("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(thread_id: uuid.UUID,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)
    return t


@router.post("/threads/{thread_id}/credits")
def thread_credits(thread_id: uuid.UUID,
                   user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    """Total credits + tokens spent across this thread's responses.

    POST per the project's POST-only convention. Powers the right panel's
    thread cost summary; sums the per-message cost the v3 chat router records.
    """
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)
    row = db.query(
        func.coalesce(func.sum(Message.cost_credits), 0),
        func.coalesce(func.sum(Message.total_tokens), 0),
    ).filter(Message.thread_id == thread_id).one()
    return {"total_credits": int(row[0]), "total_tokens": int(row[1])}


@router.post("/projects/{project_id}/credits")
def project_credits(project_id: uuid.UUID,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    """Total credits + tokens spent across ALL threads of this project.

    Powers the left panel's project cost summary. Joins messages → threads so
    the sum spans every conversation in the project.
    """
    _owned_project(db, user, project_id)
    row = (
        db.query(
            func.coalesce(func.sum(Message.cost_credits), 0),
            func.coalesce(func.sum(Message.total_tokens), 0),
        )
        .join(Thread, Thread.id == Message.thread_id)
        .filter(Thread.project_id == project_id)
        .one()
    )
    return {"total_credits": int(row[0]), "total_tokens": int(row[1])}


# Renamed from GET → POST .../messages/list: POST .../messages already posts a
# message, so the read needs a distinct path. Pagination filters ride in the
# JSON body (alongside the access_token, read by current_user).
class ListMessagesBody(BaseModel):
    before_id: int | None = None
    limit: int = 50


@router.post("/threads/{thread_id}/messages/list")
def list_messages(thread_id: uuid.UUID, body: ListMessagesBody,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    before_id = body.before_id
    limit = body.limit
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)
    q = db.query(Message).filter_by(thread_id=thread_id)
    if before_id is not None:
        q = q.filter(Message.id < before_id)
    rows = q.order_by(Message.id.desc()).limit(min(limit, 200)).all()
    # SP3 T6: include tool_calls_json so the frontend can hydrate widget bubbles
    # on page load — without this field, card_grid and other widgets would not
    # re-render after a page refresh.
    return [
        {"id": m.id, "role": m.role, "content": m.content,
         "module_tag": m.module_tag, "tool_calls_json": m.tool_calls_json,
         "cost_credits": m.cost_credits, "duration_ms": m.duration_ms,
         "total_tokens": m.total_tokens,
         "created_at": m.created_at.isoformat()}
        for m in reversed(rows)
    ]


# ----------------------------------------------------------------------------
# Streaming message endpoint (T22)
# ----------------------------------------------------------------------------

class SendMessageBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    # Structured payload from a rich widget click (FlowChart, ListEditor).
    widget_payload: dict | None = None
    # IDs of uploads the user attached to this message. The v3 chat router
    # materializes each one into an `Attachment` and ships the bytes to the
    # LLM as a proper multimodal block (Gemini inline ≤20MB / Files API
    # URI for larger files). Defaults to an empty list so existing callers
    # don't break.
    upload_ids: list[uuid.UUID] = Field(default_factory=list)


@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: uuid.UUID,
                       body: SendMessageBody,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Stream the deep-agent (v3) reply for one turn via SSE.

    v3 is the only turn path (docs/architecture/2026-06-10 deep-agent pivot):
    the skills-driven agent serves every turn and state lands in the same rows.
    chat_v3 persists the user message itself.
    """
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)

    # Credit gate. Without this a broke user runs unlimited *free* turns — the
    # end-of-turn debit clamps the charge to the balance (min(cost, balance)), so
    # at 0 credits every turn costs 0 and just streams normally. For a paid
    # product that's revenue leakage, and the user gets no signal. Block up front
    # (before send_message_v3 persists the user message, so the thread isn't left
    # with an orphaned unanswered message) and return a structured 402 the web
    # renders as an "upgrade credits" CTA.
    if (user.credit or 0) <= 0:
        raise HTTPException(
            402,
            detail={"error": {"code": "insufficient_credit",
                              "balance": user.credit or 0,
                              "message": "You're out of credits."}},
        )

    from .chat_v3 import send_message_v3
    return await send_message_v3(t, body.text, db, upload_ids=body.upload_ids)


# ----------------------------------------------------------------------------
# Thread state SSE stream (SP7 T1)
# ----------------------------------------------------------------------------

@router.post("/threads/{thread_id}/state")
async def state_stream(thread_id: uuid.UUID,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """SSE stream of context_store snapshots for the project this thread belongs to.

    Emits the current context_store snapshot as a 'context_update' event and
    terminates. The frontend uses EventSource (which auto-reconnects every ~3s)
    to receive live updates. This long-poll-via-SSE pattern keeps the generator
    finite and therefore compatible with test clients and load balancers that
    buffer responses. LISTEN/NOTIFY push can replace it later if sub-second
    latency is needed.
    """
    from ..sse import sse_pack

    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)
    project_id = t.project_id

    async def gen():
        sf = get_session_factory()
        with sf() as inner:
            cs = inner.get(ContextStore, project_id)
            snapshot = {
                "m1_topic":      cs.m1_topic      if cs else None,
                "m2_literature": cs.m2_literature if cs else None,
                "m3_design":     cs.m3_design     if cs else None,
                "m4_analysis":   cs.m4_analysis   if cs else None,
                "m5_writing":    cs.m5_writing     if cs else None,
            }
        yield sse_pack({"type": "context_update", "patch": snapshot})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
