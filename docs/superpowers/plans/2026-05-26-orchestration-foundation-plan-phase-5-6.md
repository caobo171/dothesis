# Phase 5–6: Subprocess + HTTP API (Tasks 20–26)

> Companion file to `2026-05-26-orchestration-foundation-plan.md`. Requires Phase 0–4 (Tasks 1–19) to be complete.
>
> **Stack note:** This phase uses LangChain 1.x (`langchain` 1.3+, `langchain-core` 1.4+, `langgraph` 1.2+) — pinned in Task 1.

---

## Task 20: Subprocess entrypoint (`orchestrator/__main__.py`)

**Files:**
- Create: `orchestrator/__main__.py`
- Test: `orchestrator/tests/test_subprocess.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/test_subprocess.py`:

```python
"""Smoke tests for the auto-mode subprocess entrypoint.

We don't run the full graph here (covered in integration tests). We just verify
argument parsing, brief loading, the SIGTERM handler shape, and resume routing.
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_help_flag_works():
    res = subprocess.run(
        [sys.executable, "-m", "orchestrator", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert "--auto-draft" in res.stdout
    assert "--resume-run-id" in res.stdout


def test_missing_required_args_errors():
    res = subprocess.run(
        [sys.executable, "-m", "orchestrator", "--auto-draft"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode != 0


def test_argparse_routes_auto_vs_resume(tmp_path, monkeypatch):
    """Verify the entrypoint picks the right branch based on --auto-draft / --resume-run-id."""
    from orchestrator.__main__ import build_arg_parser
    p = build_arg_parser()
    args = p.parse_args([
        "--auto-draft", "--project-id", "x", "--user-id", "y",
        "--workdir", str(tmp_path), "--brief-json", str(tmp_path / "b.json"),
    ])
    assert args.auto_draft is True
    assert args.resume_run_id is None

    args = p.parse_args(["--resume-run-id", "abc", "--workdir", str(tmp_path)])
    assert args.resume_run_id == "abc"
    assert args.auto_draft is False


def test_sigterm_handler_writes_paused_event(tmp_path, monkeypatch):
    """The handler should write a {"type":"paused",…} line before exiting."""
    from orchestrator.__main__ import _install_sigterm_handler

    events = tmp_path / "events.jsonl"

    class _Appender:
        def __init__(self, p: Path):
            self.p = p
        def write(self, obj):
            with self.p.open("a") as f:
                f.write(json.dumps(obj) + "\n")
        def close(self):
            pass

    current = {"module": "M3"}

    # Capture exit instead of letting it kill the test runner.
    exits: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exits.append(code))

    _install_sigterm_handler(_Appender(events), current)
    # Invoke the handler manually.
    handler = signal.getsignal(signal.SIGTERM)
    handler(signal.SIGTERM, None)

    assert events.exists()
    line = json.loads(events.read_text().strip())
    assert line["type"] == "paused"
    assert line["module"] == "M3"
    assert exits == [0]
```

- [ ] **Step 2: Run (fails — module missing)**

Run: `python -m pytest orchestrator/tests/test_subprocess.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the entrypoint**

Create `orchestrator/__main__.py`:

```python
"""Auto-mode subprocess entrypoint for the orchestrator.

Invoked by `api/app/job_runner.py` when a run has `mode = "auto"`. Streams
semantic events to `<workdir>/events.jsonl` so the API's existing `_monitor`
task can tail them and update DB rows. Never writes to DB directly.

Usage:
    python -m orchestrator --auto-draft \
        --project-id <uuid> --user-id <uuid> \
        --workdir <path> --brief-json <path>

    python -m orchestrator --resume-run-id <uuid> --workdir <path>
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger("orchestrator")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m orchestrator")
    p.add_argument("--auto-draft", action="store_true",
                   help="Run the full graph end-to-end in auto-mode.")
    p.add_argument("--resume-run-id", default=None,
                   help="Resume a paused run by its uuid (reads checkpoint from DB).")
    p.add_argument("--project-id", default=None)
    p.add_argument("--user-id", default=None)
    p.add_argument("--workdir", required=True)
    p.add_argument("--brief-json", default=None,
                   help="Path to JSON with {topic, language, citation_style, ...} for new auto-draft runs.")
    p.add_argument("--run-id", default=None, help="Run UUID (used as langgraph thread_id).")
    return p


def _install_sigterm_handler(appender: Any, current: dict) -> None:
    """SIGTERM → write a paused event and exit cleanly. LangGraph checkpoint
    is already on disk thanks to per-node auto-checkpointing.
    """
    def _on_term(signum, frame):
        try:
            appender.write({
                "type": "paused",
                "module": current.get("module"),
                "reason": "user_stop",
            })
        except Exception:
            logger.exception("failed to write paused event")
        finally:
            try:
                appender.close()
            except Exception:
                pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_term)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_arg_parser().parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    events_path = workdir / "events.jsonl"

    # Reuse the engine's existing JsonlAppender + JobTracker. These are
    # framework-agnostic — they just write to events.jsonl.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engine.job_io import JobStreamer, JobTracker, JsonlAppender

    appender = JsonlAppender(events_path)
    tracker = JobTracker(appender)
    streamer = JobStreamer(appender)
    current_module: dict[str, str | None] = {"module": None}
    _install_sigterm_handler(appender, current_module)

    try:
        from langchain_core.messages import HumanMessage

        from orchestrator.graph import get_auto_graph
        from orchestrator.state import ContextStore

        graph = get_auto_graph()
        run_id = args.run_id or args.resume_run_id or str(uuid4())
        config = {"configurable": {"thread_id": run_id}}

        if args.resume_run_id:
            appender.write({"type": "activity", "agent": "System",
                            "text": f"Resuming run {args.resume_run_id}"})
            # Empty input = LangGraph picks up at last checkpoint
            for event in graph.stream({}, config=config):
                _emit_event(appender, event, current_module)
        else:
            if not args.brief_json:
                raise SystemExit("--brief-json required for new auto-draft runs")
            brief = json.loads(Path(args.brief_json).read_text("utf-8"))
            initial = {
                "project_id": UUID(args.project_id) if args.project_id else None,
                "thread_id": None,
                "messages": [HumanMessage(content=brief.get("topic", ""))],
                "current_module": "M1",
                "context_store": ContextStore(),
                "mode": "auto",
                "user_intent": None,
                "pending_confirmations": [],
            }
            for event in graph.stream(initial, config=config):
                _emit_event(appender, event, current_module)

        # Final state — look up exports if M5 produced any.
        snapshot = graph.get_state(config)
        cs = snapshot.values.get("context_store")
        exports = {}
        if cs is not None and cs.m5_writing:
            for art in cs.m5_writing.get("export_artifacts", []):
                exports[art["kind"]] = art["uri"]

        # Optionally upload to S3 (only if S3 env present — keeps unit tests offline).
        if exports and "S3_BUCKET" in __import__("os").environ:
            from engine.s3_for_jobs import s3_from_env, upload_artifacts
            uploaded = upload_artifacts(s3_from_env(), workdir,
                                        f"users/{args.user_id}/projects/{args.project_id}/runs/{run_id}")
            exports.update(uploaded)

        appender.write({"type": "job_done", "exports": exports})
        return 0
    except SystemExit:
        raise
    except Exception:
        logger.exception("auto-draft failed")
        appender.write({"type": "error", "text": "orchestrator auto-draft failed",
                        "traceback": __import__("traceback").format_exc()})
        return 1
    finally:
        appender.close()


def _emit_event(appender, event: dict, current_module: dict) -> None:
    """Translate a LangGraph stream event into our events.jsonl format."""
    for node_name, payload in event.items():
        if node_name == "supervisor":
            new_mod = payload.get("current_module")
            if new_mod and new_mod != current_module.get("module"):
                current_module["module"] = new_mod
                appender.write({"type": "module_complete" if current_module.get("module") else "activity",
                                "module": new_mod,
                                "text": f"Supervisor routed to {new_mod}"})
        elif node_name in {"M1", "M2", "M3", "M4", "M5"}:
            current_module["module"] = node_name
            msgs = payload.get("messages") or []
            text = msgs[-1].content if msgs else ""
            appender.write({"type": "activity", "module": node_name,
                            "agent": f"{node_name} Agent", "text": text[:500]})


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest orchestrator/tests/test_subprocess.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/__main__.py orchestrator/tests/test_subprocess.py
git commit -m "feat(orchestrator): subprocess entrypoint with SIGTERM-aware pause/resume"
```

---

## Task 21: Chat router — project & thread CRUD

**Files:**
- Create: `api/app/routers/chat.py`
- Test: `api/tests/test_chat_router.py`

- [ ] **Step 1: Tests**

Create `api/tests/test_chat_router.py`:

```python
"""Tests for the chat router — project + thread CRUD endpoints only.

The /messages SSE streaming endpoint is covered in test_chat_messages.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Project, Thread, User
from app.db import get_session_factory


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _make_auth_cookie(monkeypatch, client):
    """Reuse existing auth fixtures to create a user + login cookie."""
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        return u


def _login(client, user):
    # Bypass real auth in tests by setting the session cookie directly.
    from app.security import create_session
    sf = get_session_factory()
    with sf() as db:
        token = create_session(db, user)
    client.cookies.set("session", token)


def test_create_project_returns_id_and_default_thread(client, monkeypatch):
    user = _make_auth_cookie(monkeypatch, client)
    _login(client, user)
    r = client.post("/api/v1/projects",
                    json={"name": "My Thesis", "field": "Marketing", "language": "vi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body
    assert body["name"] == "My Thesis"

    # A "Main" thread should exist on creation.
    sf = get_session_factory()
    with sf() as db:
        threads = db.query(Thread).filter_by(project_id=body["id"]).all()
        assert len(threads) == 1
        assert threads[0].name == "Main"


def test_get_project_returns_context_store_snapshot(client, monkeypatch):
    user = _make_auth_cookie(monkeypatch, client)
    _login(client, user)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.get(f"/api/v1/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["current_module"] == "M1"
    assert "context_store" in r.json()


def test_list_threads_for_project(client, monkeypatch):
    user = _make_auth_cookie(monkeypatch, client)
    _login(client, user)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.get(f"/api/v1/projects/{project_id}/threads")
    assert r.status_code == 200
    assert len(r.json()) == 1  # the "Main" thread


def test_create_additional_thread_in_project(client, monkeypatch):
    user = _make_auth_cookie(monkeypatch, client)
    _login(client, user)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.post(f"/api/v1/projects/{project_id}/threads",
                    json={"name": "Alt methodology"})
    assert r.status_code == 200
    assert r.json()["name"] == "Alt methodology"
    # List should now show 2.
    threads = client.get(f"/api/v1/projects/{project_id}/threads").json()
    assert len(threads) == 2


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_ENABLED", raising=False)
    c = TestClient(create_app())
    r = c.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
```

- [ ] **Step 2: Run (fails)**

Run: `cd api && python -m pytest tests/test_chat_router.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the router**

Create `api/app/routers/chat.py`:

```python
"""Chat router — project + thread CRUD + message endpoints.

Mounted under /api/v1 by main.py only when ORCHESTRATOR_ENABLED=true.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import ContextStore, Message, Project, Thread, User

router = APIRouter(tags=["chat"])


# ============================================================================
# Request / response models
# ============================================================================

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


# ============================================================================
# Helpers
# ============================================================================

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
            "m1_topic":     cs.m1_topic     if cs else None,
            "m2_literature":cs.m2_literature if cs else None,
            "m3_design":    cs.m3_design    if cs else None,
            "m4_analysis":  cs.m4_analysis  if cs else None,
            "m5_writing":   cs.m5_writing   if cs else None,
        },
        created_at=p.created_at, updated_at=p.updated_at,
    )


# ============================================================================
# Projects
# ============================================================================

@router.post("/projects", response_model=ProjectOut)
def create_project(body: CreateProjectBody,
                   user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    p = Project(user_id=user.id, name=body.name, field=body.field,
                language=body.language, citation_style=body.citation_style,
                current_module="M1", status="draft")
    db.add(p); db.flush()
    # Default Main thread.
    t = Thread(project_id=p.id, name="Main",
               langgraph_thread_id=str(uuid.uuid4()))
    db.add(t)
    # Empty context_store row.
    db.add(ContextStore(project_id=p.id))
    db.commit(); db.refresh(p)
    return _serialize_project(db, p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    return _serialize_project(db, p)


# ============================================================================
# Threads
# ============================================================================

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
    return [
        {"id": m.id, "role": m.role, "content": m.content,
         "module_tag": m.module_tag, "created_at": m.created_at.isoformat()}
        for m in reversed(rows)
    ]
```

- [ ] **Step 4: Wire into main.py — Step 25 will finish this, leave a TODO marker**

We mount the router in Task 25 (feature flag). For now, the test fixture builds `create_app()` which doesn't yet include this router, so the tests will still fail until Task 25 lands. **Skip running the tests until Task 25 completes — for now just verify the file parses.**

Run:
```bash
python -c "from api.app.routers import chat; print(chat.router.routes)"
```
Expected: prints route list.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/chat.py api/tests/test_chat_router.py
git commit -m "feat(api): chat router — project + thread CRUD (mounting in Task 25)"
```

---

## Task 22: Chat message SSE streaming endpoint

**Files:**
- Modify: `api/app/routers/chat.py` (add the streaming endpoint)
- Test: `api/tests/test_chat_messages.py`

- [ ] **Step 1: Tests**

Create `api/tests/test_chat_messages.py`:

```python
"""Tests the POST /threads/{tid}/messages SSE streaming endpoint.

We mock the orchestrator graph so tests stay offline and fast. Real graph
behavior is covered in orchestrator/tests/integration/.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Message, Project, Thread, User
from app.db import get_session_factory


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup_project(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        from app.security import create_session
        token = create_session(db, u)
    client.cookies.set("session", token)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def test_send_message_persists_user_msg_and_streams_reply(client, monkeypatch):
    pid, tid = _setup_project(client)

    # Stub the graph to yield two streamed events then halt.
    from langchain_core.messages import AIMessage
    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M1": {"messages": [AIMessage(content="Hello! What's your topic?")]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "leadership thesis"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Hello" in body  # the assistant's content was streamed

    sf = get_session_factory()
    with sf() as db:
        msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id).all()
        # 1 user + 1 assistant
        assert msgs[0].role == "user"
        assert msgs[0].content == "leadership thesis"
        assert msgs[-1].role == "assistant"
        assert "Hello" in msgs[-1].content


def _async_iter(items):
    async def _it():
        for it in items:
            yield it
    return _it()
```

- [ ] **Step 2: Run (fails — endpoint missing)**

Run: `cd api && python -m pytest tests/test_chat_messages.py -v`
Expected: FAIL — 404 or AttributeError.

- [ ] **Step 3: Append the streaming endpoint to chat.py**

Append to `api/app/routers/chat.py`:

```python
# ============================================================================
# Streaming message endpoint
# ============================================================================

from pydantic import BaseModel
from fastapi.responses import StreamingResponse


class SendMessageBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: uuid.UUID,
                       body: SendMessageBody,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Persist the user message, resume the LangGraph thread, stream agent reply.

    Output is SSE-style text/event-stream. Each chunk is a JSON dict prefixed
    by 'data: '.
    """
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

    # Buffer the assistant reply so we can persist it in full after streaming.
    assistant_chunks: list[str] = []
    final_module_tag: str | None = None

    async def gen():
        nonlocal final_module_tag
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
                        yield sse_pack({"type": "token",
                                        "module": node_name if node_name != "supervisor" else None,
                                        "text": chunk})

        # 2. Persist the full assistant reply.
        full = "".join(assistant_chunks)
        if full:
            with db.bind.connect() as conn:
                conn.execute(
                    Message.__table__.insert().values(
                        thread_id=thread_id, role="assistant",
                        content=full, module_tag=final_module_tag,
                    )
                )
                conn.commit()
        yield sse_pack({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})
```

- [ ] **Step 4: Run tests**

(After Task 25 mounts the router. For now: spot-check by importing.)
Run: `python -c "from api.app.routers.chat import send_message; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/chat.py api/tests/test_chat_messages.py
git commit -m "feat(api): streaming /threads/{tid}/messages endpoint"
```

---

## Task 23: Runs router — auto-draft start / pause / resume / status

**Files:**
- Create: `api/app/routers/runs.py`
- Test: `api/tests/test_runs_router.py`

- [ ] **Step 1: Tests**

Create `api/tests/test_runs_router.py`:

```python
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Job, Project, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=1000)
        db.add(u); db.commit()
        from app.security import create_session
        client.cookies.set("session", create_session(db, u))
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_post_run_spawns_orchestrator_subprocess(client, monkeypatch):
    pid = _setup(client)
    spawned: list = []

    def fake_spawn(db, run, brief, resume_from=None):
        run.pid = 12345
        run.status = "running"
        spawned.append({"mode": run.mode, "project_id": run.project_id,
                        "brief": brief, "resume_from": resume_from})

    monkeypatch.setattr("app.job_runner.spawn_orchestrator_run", fake_spawn)

    r = client.post(f"/api/v1/projects/{pid}/runs",
                    json={"mode": "auto", "topic": "Leadership in SMEs"})
    assert r.status_code == 200, r.text
    assert "run_id" in r.json()
    assert spawned[0]["mode"] == "auto"
    assert spawned[0]["brief"]["topic"] == "Leadership in SMEs"


def test_pause_run_calls_cancel(client, monkeypatch):
    pid = _setup(client)
    called: list = []

    def fake_cancel(db, job):
        called.append(job.id)
        job.status = "paused"

    monkeypatch.setattr("app.job_runner.spawn_orchestrator_run",
                        lambda db, run, brief, resume_from=None: setattr(run, "status", "running"))
    monkeypatch.setattr("app.job_runner.cancel_job", fake_cancel)

    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    r = client.post(f"/api/v1/runs/{rid}/pause")
    assert r.status_code == 200
    assert called  # cancel was invoked
```

- [ ] **Step 2: Run (fails)**

Run: `cd api && python -m pytest tests/test_runs_router.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the router**

Create `api/app/routers/runs.py`:

```python
"""Runs router — start/pause/resume/status for auto-mode orchestrator runs.

Coexists with the existing `jobs` router (which handles legacy engine jobs).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import job_runner
from ..db import db_session
from ..deps import current_user
from ..models import Job, Project, User

router = APIRouter(tags=["runs"])


class StartRunBody(BaseModel):
    mode: str = Field("auto", pattern="^(auto)$")
    topic: str = Field(..., min_length=1)
    language: str | None = None
    citation_style: str | None = None


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    return p


def _owned_run(db: Session, user: User, run_id: uuid.UUID) -> Job:
    j = db.get(Job, run_id)
    if not j or j.project_id is None:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, j.project_id)
    return j


@router.post("/projects/{project_id}/runs")
def start_run(project_id: uuid.UUID, body: StartRunBody,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    run = Job(
        paper_id=None,                  # new orchestrator runs may not have a paper_id
        project_id=project_id,
        mode=body.mode,
        status="queued",
        langgraph_thread_id=str(uuid.uuid4()),
    )
    db.add(run); db.flush()
    brief = {
        "topic": body.topic,
        "language": body.language or p.language,
        "citation_style": body.citation_style or p.citation_style,
    }
    job_runner.spawn_orchestrator_run(db, run, brief)
    db.commit()
    return {"run_id": str(run.id), "status": run.status}


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: uuid.UUID,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    run = _owned_run(db, user, run_id)
    if run.status not in {"queued", "running"}:
        return {"status": run.status}
    job_runner.cancel_job(db, run)        # existing SIGTERM helper
    return {"status": "pausing"}


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: uuid.UUID,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    run = _owned_run(db, user, run_id)
    if run.status != "paused":
        raise HTTPException(409,
                            detail={"error": {"code": "not_paused",
                                              "message": f"run is {run.status}"}})
    job_runner.spawn_orchestrator_run(db, run, brief={}, resume_from=str(run.id))
    db.commit()
    return {"status": run.status}


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID,
            user: User = Depends(current_user),
            db: Session = Depends(db_session)):
    j = _owned_run(db, user, run_id)
    return {
        "id": str(j.id), "project_id": str(j.project_id) if j.project_id else None,
        "status": j.status, "phase": j.phase, "progress": j.progress,
        "mode": j.mode,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "error_text": j.error_text,
        "events_url": f"/api/v1/jobs/{j.id}/events",   # reuses existing SSE bridge
    }
```

- [ ] **Step 4: Run (deferred to Task 25 which mounts the router)**

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/runs.py api/tests/test_runs_router.py
git commit -m "feat(api): runs router for auto-mode orchestrator runs"
```

---

## Task 24: `job_runner.py` — orchestrator subprocess support

**Files:**
- Modify: `api/app/job_runner.py`
- Test: `api/tests/test_job_runner.py` (extends existing)

- [ ] **Step 1: Append tests**

Append to `api/tests/test_job_runner.py`:

```python
import uuid
from unittest.mock import patch

from app.db import get_session_factory
from app.job_runner import spawn_orchestrator_run
from app.models import Job, Project, User


def test_spawn_orchestrator_uses_orchestrator_module(monkeypatch, tmp_path):
    captured: dict = {}

    class _FakeProc:
        pid = 99999

    def fake_popen(cmd, cwd, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return _FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("app.job_runner.start_monitor", lambda jid: None)

    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x"); db.add(u); db.flush()
        p = Project(user_id=u.id, name="X", language="en", citation_style="apa")
        db.add(p); db.flush()
        run = Job(project_id=p.id, mode="auto", status="queued",
                  langgraph_thread_id=str(uuid.uuid4()))
        db.add(run); db.flush()
        spawn_orchestrator_run(db, run, {"topic": "Test"})

    assert "-m" in captured["cmd"]
    idx = captured["cmd"].index("-m")
    assert captured["cmd"][idx + 1] == "orchestrator"
    assert "--auto-draft" in captured["cmd"]


def test_spawn_orchestrator_resume_passes_run_id(monkeypatch, tmp_path):
    captured: dict = {}

    class _FakeProc: pid = 88888
    monkeypatch.setattr("subprocess.Popen",
                        lambda cmd, cwd, env: captured.setdefault("cmd", cmd) or _FakeProc())
    monkeypatch.setattr("app.job_runner.start_monitor", lambda jid: None)

    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x"); db.add(u); db.flush()
        p = Project(user_id=u.id, name="X", language="en", citation_style="apa")
        db.add(p); db.flush()
        run = Job(project_id=p.id, mode="auto", status="paused",
                  langgraph_thread_id=str(uuid.uuid4()))
        db.add(run); db.flush()
        spawn_orchestrator_run(db, run, brief={}, resume_from=str(run.id))

    assert "--resume-run-id" in captured["cmd"]
```

- [ ] **Step 2: Run (fails)**

Run: `cd api && python -m pytest tests/test_job_runner.py -v -k orchestrator`
Expected: FAIL — `spawn_orchestrator_run` doesn't exist.

- [ ] **Step 3: Add `spawn_orchestrator_run` to `job_runner.py`**

Append to `api/app/job_runner.py`:

```python
def spawn_orchestrator_run(db: Session, run: Job, brief: dict,
                           resume_from: str | None = None) -> None:
    """Spawn `python -m orchestrator` as a subprocess for an auto-mode run.

    Mirrors `spawn_job` but uses the orchestrator entrypoint. The events.jsonl
    contract is identical so `_monitor` keeps working unchanged.
    """
    settings = get_settings()
    workdir = settings.job_workdir_root / str(run.id)
    workdir.mkdir(parents=True, exist_ok=True)
    if not resume_from:
        (workdir / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    env = os.environ.copy()
    env["RUN_ID"] = str(run.id)
    if run.project_id:
        env["PROJECT_ID"] = str(run.project_id)
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    env["AWS_REGION"] = settings.aws_region
    env["S3_BUCKET"] = settings.s3_bucket
    env["S3_PREFIX"] = settings.s3_prefix
    env["AWS_ACCESS_KEY"] = settings.aws_access_key
    env["AWS_SECRET_KEY"] = settings.aws_secret_key
    if settings.gemini_api_key:
        env["GEMINI_API_KEY"] = settings.gemini_api_key
        env["GOOGLE_API_KEY"] = settings.gemini_api_key
    if settings.openai_api_key:
        env["OPENAI_API_KEY"] = settings.openai_api_key

    # Identify owning user by walking project_id → user_id
    user_id = None
    if run.project_id:
        from .models import Project
        proj = db.get(Project, run.project_id)
        user_id = str(proj.user_id) if proj else None

    cmd = [sys.executable, "-m", "orchestrator",
           "--workdir", str(workdir),
           "--run-id", str(run.id)]
    if resume_from:
        cmd.extend(["--resume-run-id", resume_from])
    else:
        cmd.extend([
            "--auto-draft",
            "--brief-json", str(workdir / "brief.json"),
            "--project-id", str(run.project_id) if run.project_id else "",
            "--user-id", user_id or "",
        ])

    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    run.pid = proc.pid
    run.workdir = str(workdir)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(run.id)
```

Also extend `_monitor` to recognize the new `paused` event type. Edit the existing `_monitor` function — find the block that processes events and add a branch for `type == "paused"`:

```python
    # Inside _monitor's event loop, where event type is dispatched:
    if event.get("type") == "paused":
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "paused"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
        return  # exit monitor loop
```

- [ ] **Step 4: Run tests**

Run: `cd api && python -m pytest tests/test_job_runner.py -v`
Expected: PASS (the new tests plus existing).

- [ ] **Step 5: Commit**

```bash
git add api/app/job_runner.py api/tests/test_job_runner.py
git commit -m "feat(api): job_runner.spawn_orchestrator_run + paused event handling"
```

---

## Task 25: Feature flag + router mounting

**Files:**
- Modify: `api/app/settings.py`
- Modify: `api/app/main.py`

- [ ] **Step 1: Tests already exist (from Tasks 21–23)**

The chat + runs router tests gate themselves on `ORCHESTRATOR_ENABLED=true`. They'll start passing as soon as we mount.

- [ ] **Step 2: Add the setting**

Append to `api/app/settings.py` inside the Settings class (matching existing pattern):

```python
    orchestrator_enabled: bool = False
    langsmith_api_key: str | None = None
    orchestrator_pg_pool_max: int = 10
```

- [ ] **Step 3: Mount the routers conditionally in main.py**

Edit `api/app/main.py` — in `create_app()`, before the `return app` line, add:

```python
    if settings.orchestrator_enabled:
        from .routers import chat as chat_router
        from .routers import runs as runs_router
        app.include_router(chat_router.router, prefix="/api/v1")
        app.include_router(runs_router.router, prefix="/api/v1")
```

- [ ] **Step 4: Run all router tests**

Run:
```bash
cd api && python -m pytest tests/test_chat_router.py tests/test_chat_messages.py tests/test_runs_router.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/main.py api/app/settings.py
git commit -m "feat(api): ORCHESTRATOR_ENABLED feature flag + conditional router mount"
```

---

## Task 26: App startup hooks (PostgresSaver + graph cache warming)

**Files:**
- Modify: `api/app/main.py`

- [ ] **Step 1: Test**

Append to `api/tests/test_health.py`:

```python
def test_orchestrator_graph_compiles_at_startup(monkeypatch):
    """When ORCHESTRATOR_ENABLED is true, the graph cache should be primed at lifespan start."""
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", monkeypatch.getenv("DATABASE_URL") or "postgresql://localhost/x")

    # Stub the heavy PostgresSaver path
    called: list[str] = []
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph",
        lambda: called.append("interactive") or object(),
    )
    monkeypatch.setattr(
        "orchestrator.graph.get_auto_graph",
        lambda: called.append("auto") or object(),
    )

    from app.main import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app()) as c:
        c.get("/api/v1/health")  # any request triggers lifespan
    assert "interactive" in called
```

- [ ] **Step 2: Run (fails — startup hook missing)**

Run: `cd api && python -m pytest tests/test_health.py::test_orchestrator_graph_compiles_at_startup -v`
Expected: FAIL.

- [ ] **Step 3: Add the startup hook to main.py**

Edit `api/app/main.py` — modify the `lifespan` async context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.job_workdir_root.mkdir(parents=True, exist_ok=True)

    # Orchestrator: prime the graph cache at startup so first chat turn isn't slow.
    # PostgresSaver.setup() runs as a side effect of get_*_graph().
    if settings.orchestrator_enabled:
        try:
            from orchestrator.graph import get_auto_graph, get_interactive_graph
            get_interactive_graph()
            get_auto_graph()
        except Exception:
            import logging
            logging.exception("orchestrator graph init failed (continuing without it)")

    yield
```

- [ ] **Step 4: Run**

Run: `cd api && python -m pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/main.py api/tests/test_health.py
git commit -m "feat(api): warm orchestrator graph cache at startup when flag enabled"
```

---

End of Phase 5–6 (Tasks 20–26). Continue to `2026-05-26-orchestration-foundation-plan-phase-7.md` for Tasks 27–32 (integration tests + migration test).
