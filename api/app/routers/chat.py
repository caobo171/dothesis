"""Chat router — project + thread CRUD + streaming message endpoint.

Mounted under /api/v1 by main.py only when ORCHESTRATOR_ENABLED=true.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
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


def _serialize_project(db: Session, p: Project) -> ProjectOut:
    cs = db.get(ContextStore, p.id)
    return ProjectOut(
        id=p.id, name=p.name, field=p.field, language=p.language,
        citation_style=p.citation_style, status=p.status,
        current_module=p.current_module,
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
    db.commit(); db.refresh(p)
    return _serialize_project(db, p)


@router.get("/projects", response_model=list[ProjectOut])
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
    return [_serialize_project(db, p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    return _serialize_project(db, p)


@router.get("/projects/{project_id}/artifacts")
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


@router.get("/projects/{project_id}/impact/{artifact}")
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

@router.get("/projects/{project_id}/threads", response_model=list[ThreadOut])
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


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(thread_id: uuid.UUID,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)
    return t


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: uuid.UUID, before_id: int | None = None, limit: int = 50,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
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
         "created_at": m.created_at.isoformat()}
        for m in reversed(rows)
    ]


# ----------------------------------------------------------------------------
# Streaming message endpoint (T22)
# ----------------------------------------------------------------------------

class SendMessageBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: uuid.UUID,
                       body: SendMessageBody,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Persist user message, resume the LangGraph thread, stream agent reply via SSE."""
    from langchain_core.messages import HumanMessage
    from orchestrator.graph import get_interactive_graph
    from ..sse import sse_pack

    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)

    # 1. Persist the user message.
    db.add(Message(thread_id=thread_id, role="user", content=body.text))
    db.commit()

    # Seed the LangGraph state with the project's ContextStore — but ONLY on the
    # first turn for this thread. OrchestratorState.context_store has no
    # reducer, so passing it in the input on every turn would clobber the
    # checkpoint's accumulated state (_awaiting_field markers, partial slices)
    # and the agent would loop forever asking the same question. Subsequent
    # turns rely on the checkpoint resuming with whatever the previous turn
    # wrote.
    from orchestrator.state import ContextStore as OrchestratorContextStore
    from ..models import ContextStore as DbContextStore
    db_cs = db.get(DbContextStore, t.project_id)

    graph = get_interactive_graph()
    config = {"configurable": {"thread_id": t.langgraph_thread_id}}

    existing = await graph.aget_state(config)
    is_first_turn = not existing or not existing.values
    initial_context_store = OrchestratorContextStore(
        m1_topic=(db_cs.m1_topic if db_cs else None),
        m2_literature=(db_cs.m2_literature if db_cs else None),
        m3_design=(db_cs.m3_design if db_cs else None),
        m4_analysis=(db_cs.m4_analysis if db_cs else None),
        m5_writing=(db_cs.m5_writing if db_cs else None),
    )

    assistant_chunks: list[str] = []
    final_module_tag: str | None = None
    # SP3 T6: capture the last tool_calls_json hint emitted by the agent so we
    # can persist it alongside the assistant message and hydrate widgets on
    # page reload.  None when no module attached a render hint (→ SQL NULL,
    # safe for the nullable JSONB column).
    final_tool_calls: dict | None = None

    async def gen():
        nonlocal final_module_tag, final_tool_calls
        import asyncio as _asyncio
        import logging
        log = logging.getLogger(__name__)

        # P3: shared queue multiplexes graph events + engine progress so SSE
        # ordering reflects real-time chronology (a progress beat emitted
        # mid-scout reaches the user BEFORE the scout's final node update,
        # even though astream blocks until the node returns).
        events_q: _asyncio.Queue = _asyncio.Queue()
        loop = _asyncio.get_running_loop()

        def progress_emitter(payload: dict) -> None:
            """Called by engine code via engine.utils.progress; runs on the
            LangGraph executor thread, NOT the asyncio loop. Bridge back to
            the loop via call_soon_threadsafe so the queue stays consistent."""
            try:
                loop.call_soon_threadsafe(
                    events_q.put_nowait, ("progress", payload))
            except Exception:  # noqa: BLE001
                pass

        try:
            graph_input: dict = {
                "messages": [HumanMessage(content=body.text)],
                "mode": "interactive",
                # Forward the per-request progress emitter into graph state.
                # M2Agent reads it and passes through to phase2's scout.
                "_progress_emitter": progress_emitter,
            }
            if is_first_turn:
                graph_input["context_store"] = initial_context_store
                graph_input["project_id"] = t.project_id
                # Enter-at-any-step: seed the thread's target so the supervisor's
                # planner routes toward it (and backfills prerequisites). Seeded
                # only on the first turn — the checkpoint owns it afterwards and
                # the supervisor clears it once the target is reached.
                if t.target_artifact:
                    graph_input["target_artifact"] = t.target_artifact

            async def _pump_graph():
                """Drain graph.astream into the shared queue. A sentinel
                marks completion so the consumer below can exit cleanly."""
                try:
                    async for ev in graph.astream(
                        graph_input, config=config, stream_mode="updates",
                    ):
                        await events_q.put(("graph", ev))
                finally:
                    await events_q.put(("done", None))

            pump_task = _asyncio.create_task(_pump_graph())

            while True:
                kind, item = await events_q.get()
                if kind == "done":
                    break
                if kind == "progress":
                    # Live engine progress (e.g. M2 scout): forward verbatim.
                    yield sse_pack({"type": "progress", "payload": item})
                    continue
                # kind == "graph" — original node-update handling.
                event = item
                for node_name, payload in event.items():
                    # LangGraph v1 emits non-dict payloads for special signals like
                    # __interrupt__ (a tuple of Interrupt objects) when the graph is
                    # built with interrupt_before. Skip — the chat surface only
                    # forwards regular node updates as SSE tokens. (When we wire
                    # the interrupt UX, branch here on node_name == "__interrupt__".)
                    if not isinstance(payload, dict):
                        continue
                    if node_name in {"M1", "M2", "M3", "M4", "M5"}:
                        final_module_tag = node_name
                    msgs = payload.get("messages") or []
                    for m in msgs:
                        chunk = getattr(m, "content", "")
                        if chunk:
                            assistant_chunks.append(chunk)
                            yield sse_pack({
                                "type": "token",
                                "module": node_name if node_name != "supervisor" else None,
                                "text": chunk,
                            })

                        # SP3 T6: forward render hint if the agent attached one.
                        # additional_kwargs["tool_calls_json"] is set by M1 (and
                        # future modules) when they want the frontend to show a
                        # structured widget (card_grid, scale, etc.).
                        tc = getattr(m, "additional_kwargs", {}).get("tool_calls_json")
                        if tc:
                            final_tool_calls = tc
                            yield sse_pack({"type": "tool_calls", "payload": tc})
            # Re-raise any exception the pump task captured.
            await pump_task
        except Exception as e:
            # Surface graph failures to the client instead of silently closing the
            # stream. Without this the browser sees an empty SSE response and the
            # user thinks the assistant just didn't reply.
            log.exception("graph.astream crashed for thread %s", thread_id)
            yield sse_pack({
                "type": "error",
                "message": f"{type(e).__name__}: {e}",
            })
            return

        # Persist the assistant reply (full text + any widget hint).
        full = "".join(assistant_chunks)
        if full:
            with db.bind.connect() as conn:
                conn.execute(
                    Message.__table__.insert().values(
                        thread_id=thread_id, role="assistant",
                        content=full, module_tag=final_module_tag,
                        tool_calls_json=final_tool_calls,
                    )
                )
                conn.commit()

        # Sync the agent's updated context_store back to the DB row so other
        # threads (and future first-turn seeds) see the latest progress. The
        # checkpoint is the source of truth between turns; the DB row is the
        # cross-thread durable copy.
        final_state = await graph.aget_state(config)
        cs_after = (final_state.values or {}).get("context_store") if final_state else None
        if cs_after is not None:
            with db.bind.connect() as conn:
                conn.execute(
                    DbContextStore.__table__.update()
                    .where(DbContextStore.__table__.c.project_id == t.project_id)
                    .values(
                        m1_topic=cs_after.m1_topic,
                        m2_literature=cs_after.m2_literature,
                        m3_design=cs_after.m3_design,
                        m4_analysis=cs_after.m4_analysis,
                        m5_writing=cs_after.m5_writing,
                    )
                )
                conn.commit()
        yield sse_pack({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ----------------------------------------------------------------------------
# Thread state SSE stream (SP7 T1)
# ----------------------------------------------------------------------------

@router.get("/threads/{thread_id}/state")
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
