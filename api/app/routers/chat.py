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


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    return _serialize_project(db, p)


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

    graph = get_interactive_graph()
    config = {"configurable": {"thread_id": t.langgraph_thread_id}}

    assistant_chunks: list[str] = []
    final_module_tag: str | None = None
    # SP3 T6: capture the last tool_calls_json hint emitted by the agent so we
    # can persist it alongside the assistant message and hydrate widgets on
    # page reload.  None when no module attached a render hint (→ SQL NULL,
    # safe for the nullable JSONB column).
    final_tool_calls: dict | None = None

    async def gen():
        nonlocal final_module_tag, final_tool_calls
        async for event in graph.astream(
            {"messages": [HumanMessage(content=body.text)], "mode": "interactive"},
            config=config,
            stream_mode="updates",
        ):
            for node_name, payload in event.items():
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
