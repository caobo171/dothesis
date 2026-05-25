# Phase 0–2: Setup, models, schemas, tools (Tasks 1–11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Companion file to `2026-05-26-orchestration-foundation-plan.md`.

---

## Task 1: Dependencies & orchestrator package skeleton

**Files:**
- Create: `orchestrator/__init__.py`
- Create: `orchestrator/pyproject.toml`
- Create: `orchestrator/tests/__init__.py`
- Create: `orchestrator/tests/conftest.py`
- Modify: `requirements.txt`
- Modify: `api/pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add a smoke test for the package**

Create `orchestrator/tests/test_smoke.py`:

```python
def test_package_imports():
    import orchestrator
    assert hasattr(orchestrator, "__version__")
```

- [ ] **Step 2: Run it (should fail because package doesn't exist)**

Run: `python -m pytest orchestrator/tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator'`

- [ ] **Step 3: Create the package skeleton**

Create `orchestrator/__init__.py`:

```python
"""Chat-based research orchestrator built on LangGraph."""
__version__ = "0.1.0"
```

Create `orchestrator/tests/__init__.py` (empty).

Create `orchestrator/tests/conftest.py`:

```python
"""Shared pytest fixtures for orchestrator tests."""
import pytest


@pytest.fixture
def fake_llm_responses():
    """Override per-test to inject responses into FakeListChatModel."""
    return ["test response"]
```

Create `orchestrator/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=70.0"]
build-backend = "setuptools.build_meta"

[project]
name = "dothesis-orchestrator"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  # LangChain 1.x stack (verified May 2026 PyPI versions)
  "langchain>=1.3.0,<2",
  "langchain-core>=1.4.0,<2",
  "langgraph>=1.2.0,<2",
  "langgraph-checkpoint>=4.1.0,<5",
  "langgraph-checkpoint-postgres>=3.1.0,<4",
  "langchain-google-genai>=4.1.0,<5",
  "pydantic>=2.9",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.2",
  "psycopg-pool>=3.2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
]

[tool.setuptools]
packages = ["orchestrator"]
```

- [ ] **Step 4: Add deps to root requirements + api pyproject**

Modify `requirements.txt` — append at end:

```
# === LangChain 1.x orchestrator (sub-project 1) ===
langchain>=1.3.0,<2
langchain-core>=1.4.0,<2
langgraph>=1.2.0,<2
langgraph-checkpoint>=4.1.0,<5
langgraph-checkpoint-postgres>=3.1.0,<4
langchain-google-genai>=4.1.0,<5
```

Modify `api/pyproject.toml` — add to `dependencies`:

```
  "langchain>=1.3.0,<2",
  "langchain-core>=1.4.0,<2",
  "langgraph>=1.2.0,<2",
  "langgraph-checkpoint>=4.1.0,<5",
  "langgraph-checkpoint-postgres>=3.1.0,<4",
  "langchain-google-genai>=4.1.0,<5",
```

Modify `.env.example` — append:

```
# Orchestrator (sub-project 1) — set to true to enable new chat routes
ORCHESTRATOR_ENABLED=false
LANGSMITH_API_KEY=
```

- [ ] **Step 5: Install + verify**

Run:
```bash
pip install -r requirements.txt
pip install -e orchestrator
python -m pytest orchestrator/tests/test_smoke.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add orchestrator/ requirements.txt api/pyproject.toml .env.example
git commit -m "feat(orchestrator): scaffold package + LangGraph deps"
```

---

## Task 2: Alembic migration for new tables

**Files:**
- Create: `api/migrations/versions/20260526_add_orchestrator_tables.py`
- Test: `orchestrator/tests/test_migration.py`

- [ ] **Step 1: Write the migration smoke test**

Create `orchestrator/tests/test_migration.py`:

```python
"""Verifies the orchestrator migration runs up/down/up cleanly."""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_env(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.chdir(REPO_ROOT / "api")
    return pg_url


def _alembic(args: list[str]) -> None:
    subprocess.run(["alembic", *args], check=True)


def test_migration_up_down_up_clean(alembic_env):
    _alembic(["upgrade", "head"])
    eng = create_engine(alembic_env)
    insp = inspect(eng)
    for t in ("projects", "threads", "messages", "context_store"):
        assert t in insp.get_table_names(), f"missing table {t}"
    job_cols = {c["name"] for c in insp.get_columns("jobs")}
    for c in ("project_id", "thread_id", "mode", "langgraph_thread_id"):
        assert c in job_cols, f"jobs missing column {c}"

    _alembic(["downgrade", "-1"])
    insp = inspect(eng)
    for t in ("projects", "threads", "messages", "context_store"):
        assert t not in insp.get_table_names(), f"{t} should be gone after downgrade"

    _alembic(["upgrade", "head"])  # re-up must be idempotent


def test_papers_backfill_into_projects(alembic_env):
    _alembic(["downgrade", "base"])
    eng = create_engine(alembic_env)
    # Need users table for FK. Bring schema to the revision *just before* ours.
    _alembic(["upgrade", "-1"])  # head-1 = the auth/etc. migration directly before this
    with eng.begin() as cx:
        cx.execute(text(
            "INSERT INTO users(id,email,username,password_hash) "
            "VALUES (gen_random_uuid(),'t@x','tester','x')"
        ))
        uid = cx.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        cx.execute(text(
            "INSERT INTO papers(id,user_id,topic,academic_level,language,citation_style,model) "
            "VALUES (gen_random_uuid(), :uid, 'Test topic', 'master', 'en', 'apa', 'gemini')"
        ), {"uid": uid})

    _alembic(["upgrade", "head"])
    with eng.begin() as cx:
        n_projects = cx.execute(text("SELECT COUNT(*) FROM projects")).scalar()
        n_threads = cx.execute(text("SELECT COUNT(*) FROM threads")).scalar()
        n_ctx = cx.execute(text("SELECT COUNT(*) FROM context_store")).scalar()
    assert n_projects == 1
    assert n_threads == 1
    assert n_ctx == 1
```

Reuses the `pg_url` fixture defined in `api/tests/conftest.py` — add `conftest.py` next to the file:

Create `orchestrator/tests/conftest.py` (replace existing):

```python
"""Shared pytest fixtures for orchestrator tests.

Reuses the testcontainers Postgres fixture pattern from api/tests/conftest.py.
"""
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture
def fake_llm_responses():
    return ["test response"]
```

- [ ] **Step 2: Run it (should fail because migration doesn't exist)**

Run: `python -m pytest orchestrator/tests/test_migration.py::test_migration_up_down_up_clean -v`
Expected: FAIL — alembic error about unknown revision

- [ ] **Step 3: Locate the current head revision**

Run: `cd api && alembic heads`
Note the revision id (let's call it `<PREV_HEAD>`).

- [ ] **Step 4: Write the migration**

Create `api/migrations/versions/20260526_add_orchestrator_tables.py`:

```python
"""add orchestrator tables (projects, threads, messages, context_store) and extend jobs

Revision ID: 20260526_orch01
Revises: <PREV_HEAD>
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260526_orch01"
down_revision = "<PREV_HEAD>"   # ← replace with the value from Step 3
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("field", sa.String(64), nullable=True),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("citation_style", sa.String(16), nullable=False, server_default="apa"),
        sa.Column("research_approach", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("current_module", sa.String(8), nullable=False, server_default="M1"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False, server_default="Main"),
        sa.Column("langgraph_thread_id", sa.Text, nullable=False, unique=True),
        sa.Column("parent_thread_id", UUID(as_uuid=True), nullable=True),
        sa.Column("forked_at_message_id", sa.BigInteger, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("thread_id", UUID(as_uuid=True),
                  sa.ForeignKey("threads.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("module_tag", sa.String(8), nullable=True),
        sa.Column("tool_calls_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "context_store",
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("m1_topic", JSONB, nullable=True),
        sa.Column("m2_literature", JSONB, nullable=True),
        sa.Column("m3_design", JSONB, nullable=True),
        sa.Column("m4_analysis", JSONB, nullable=True),
        sa.Column("m5_writing", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Backfill: each existing paper → one project + one (archived) "Main" thread
    # + a context_store row marked M5-confirmed (since the paper already has output).
    op.execute("""
        INSERT INTO projects (id, user_id, name, field, language, citation_style,
                              status, current_module, created_at, updated_at)
        SELECT id, user_id, COALESCE(topic, 'Untitled'),
               NULL, language, citation_style,
               status, 'DONE', created_at, updated_at
        FROM papers
    """)
    op.execute("""
        INSERT INTO threads (id, project_id, name, langgraph_thread_id, status, created_at, last_active_at)
        SELECT gen_random_uuid(), p.id, 'Main', p.id::text, 'archived',
               p.created_at, p.updated_at
        FROM papers p
    """)
    op.execute("""
        INSERT INTO context_store (project_id, m5_writing, updated_at)
        SELECT id, jsonb_build_object('confirmed_at', updated_at::text), updated_at
        FROM papers
    """)

    # Extend jobs table — nullable so legacy engine rows keep working.
    op.add_column("jobs", sa.Column("project_id", UUID(as_uuid=True), nullable=True))
    op.add_column("jobs", sa.Column("thread_id",  UUID(as_uuid=True), nullable=True))
    op.add_column("jobs", sa.Column("mode",       sa.String(16),       nullable=True))
    op.add_column("jobs", sa.Column("langgraph_thread_id", sa.Text,    nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "langgraph_thread_id")
    op.drop_column("jobs", "mode")
    op.drop_column("jobs", "thread_id")
    op.drop_column("jobs", "project_id")
    op.drop_table("context_store")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("projects")
```

- [ ] **Step 5: Run the test**

Run: `python -m pytest orchestrator/tests/test_migration.py -v`
Expected: PASS for both tests.

- [ ] **Step 6: Commit**

```bash
git add api/migrations/versions/20260526_add_orchestrator_tables.py \
        orchestrator/tests/test_migration.py orchestrator/tests/conftest.py
git commit -m "feat(orchestrator): alembic migration for projects/threads/messages/context_store"
```

---

## Task 3: SQLAlchemy models

**Files:**
- Modify: `api/app/models.py`
- Test: `api/tests/test_models.py`

- [ ] **Step 1: Write tests for the new models**

Append to `api/tests/test_models.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Project, Thread, Message, ContextStore, User


def _make_user(db: Session) -> User:
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
             password_hash="x")
    db.add(u); db.flush()
    return u


def test_project_thread_message_roundtrip():
    with Session(get_engine()) as db:
        u = _make_user(db)
        p = Project(user_id=u.id, name="Test", language="en", citation_style="apa")
        db.add(p); db.flush()
        t = Thread(project_id=p.id, name="Main", langgraph_thread_id=f"lg-{uuid.uuid4()}")
        db.add(t); db.flush()
        m = Message(thread_id=t.id, role="user", content="hello")
        db.add(m); db.commit()

        got = db.scalar(select(Message).where(Message.thread_id == t.id))
        assert got.content == "hello"
        assert got.role == "user"
        assert got.created_at is not None


def test_context_store_jsonb_roundtrip():
    with Session(get_engine()) as db:
        u = _make_user(db)
        p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
        db.add(p); db.flush()
        cs = ContextStore(project_id=p.id,
                          m1_topic={"research_title": "X", "objectives": ["a", "b"]})
        db.add(cs); db.commit()

        got = db.get(ContextStore, p.id)
        assert got.m1_topic == {"research_title": "X", "objectives": ["a", "b"]}
        assert got.m2_literature is None


def test_threads_can_have_many_per_project():
    with Session(get_engine()) as db:
        u = _make_user(db)
        p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
        db.add(p); db.flush()
        for n in ("Main", "Alt", "Experiment"):
            db.add(Thread(project_id=p.id, name=n,
                          langgraph_thread_id=f"lg-{uuid.uuid4()}"))
        db.commit()
        rows = db.scalars(select(Thread).where(Thread.project_id == p.id)).all()
        assert {r.name for r in rows} == {"Main", "Alt", "Experiment"}
```

- [ ] **Step 2: Run (should fail — models not defined)**

Run: `cd api && python -m pytest tests/test_models.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Add the new models**

Append to `api/app/models.py`:

```python
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(16), nullable=False, server_default="en")
    citation_style: Mapped[str] = mapped_column(String(16), nullable=False, server_default="apa")
    research_approach: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    current_module: Mapped[str] = mapped_column(String(8), nullable=False, server_default="M1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, server_default="Main")
    langgraph_thread_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    forked_at_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    module_tag: Mapped[str | None] = mapped_column(String(8))
    tool_calls_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContextStore(Base):
    __tablename__ = "context_store"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    m1_topic: Mapped[dict | None] = mapped_column(JSONB)
    m2_literature: Mapped[dict | None] = mapped_column(JSONB)
    m3_design: Mapped[dict | None] = mapped_column(JSONB)
    m4_analysis: Mapped[dict | None] = mapped_column(JSONB)
    m5_writing: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Extend the existing `Job` model — add these columns to the `Job` class:

```python
    # Orchestrator extensions (sub-project 1). All nullable so legacy engine
    # jobs (mode IS NULL) keep working unchanged.
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    mode: Mapped[str | None] = mapped_column(String(16))
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 4: Run tests**

Run: `cd api && python -m pytest tests/test_models.py -v`
Expected: PASS (the three new tests, plus all existing).

- [ ] **Step 5: Commit**

```bash
git add api/app/models.py api/tests/test_models.py
git commit -m "feat(orchestrator): SQLAlchemy models for projects/threads/messages/context_store"
```

---

## Task 4: OrchestratorState + ContextStore Pydantic

**Files:**
- Create: `orchestrator/state.py`
- Test: `orchestrator/tests/test_state.py`

- [ ] **Step 1: Write tests**

Create `orchestrator/tests/test_state.py`:

```python
from datetime import datetime
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.state import (
    ContextStore, OrchestratorState, get_module_slice, next_unconfirmed_module,
)


def test_context_store_default_empty():
    cs = ContextStore()
    for m in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(cs, m) is None


def test_context_store_roundtrip_jsonb():
    cs = ContextStore(m1_topic={"research_title": "X"})
    blob = cs.model_dump()
    assert blob["m1_topic"] == {"research_title": "X"}
    cs2 = ContextStore.model_validate(blob)
    assert cs2.m1_topic == {"research_title": "X"}


def test_next_unconfirmed_walks_in_order():
    cs = ContextStore()
    assert next_unconfirmed_module(cs) == "M1"
    cs.m1_topic = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M2"
    cs.m2_literature = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m3_design = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m4_analysis = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M5"
    cs.m5_writing = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "DONE"


def test_get_module_slice_returns_only_relevant_field():
    cs = ContextStore(m1_topic={"a": 1}, m2_literature={"b": 2})
    assert get_module_slice(cs, "M1") == {"a": 1}
    assert get_module_slice(cs, "M2") == {"b": 2}
    assert get_module_slice(cs, "M3") == {}


def test_orchestrator_state_construction():
    state: OrchestratorState = {
        "project_id": uuid4(),
        "thread_id": uuid4(),
        "messages": [HumanMessage(content="hi")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    assert state["current_module"] == "M1"
    assert state["mode"] == "interactive"
```

- [ ] **Step 2: Run (fails — state.py missing)**

Run: `python -m pytest orchestrator/tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `orchestrator/state.py`**

Create `orchestrator/state.py`:

```python
"""Orchestrator state model — in-memory graph state + project-shared context store."""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


ModuleKey = Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
Mode = Literal["interactive", "auto"]
_MODULES: tuple[ModuleKey, ...] = ("M1", "M2", "M3", "M4", "M5")


class ContextStore(BaseModel):
    """Project-shared confirmed module outputs.

    Stored in the `context_store` DB table as JSONB columns. Threads of the same
    project read & write this concurrently — `orchestrator/concurrency.py` enforces
    first-confirm-wins on writes.
    """
    m1_topic: dict | None = None
    m2_literature: dict | None = None
    m3_design: dict | None = None
    m4_analysis: dict | None = None
    m5_writing: dict | None = None


class OrchestratorState(TypedDict, total=False):
    """LangGraph in-memory state for a single graph invocation."""
    project_id: UUID
    thread_id: UUID
    messages: Annotated[list[BaseMessage], add_messages]
    current_module: ModuleKey
    context_store: ContextStore
    mode: Mode
    user_intent: str | None
    pending_confirmations: list[str]


_MODULE_TO_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


def get_module_slice(cs: ContextStore, module: ModuleKey) -> dict:
    """Read the partial schema for the given module. Returns {} if untouched.

    Agents call this instead of touching ContextStore directly so we have a
    single chokepoint for any future access-control or redaction.
    """
    if module == "DONE":
        return {}
    return getattr(cs, _MODULE_TO_FIELD[module]) or {}


def is_module_confirmed(cs: ContextStore, module: ModuleKey) -> bool:
    if module == "DONE":
        return True
    return bool(get_module_slice(cs, module).get("confirmed_at"))


def next_unconfirmed_module(cs: ContextStore) -> ModuleKey:
    """Walk M1..M5 in order; return the first not-yet-confirmed module, or DONE."""
    for m in _MODULES:
        if not is_module_confirmed(cs, m):
            return m
    return "DONE"
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/test_state.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/state.py orchestrator/tests/test_state.py
git commit -m "feat(orchestrator): OrchestratorState + ContextStore + module helpers"
```

---

## Task 5: Module output schemas (M1–M5 + common enums)

**Files:**
- Create: `orchestrator/schemas/__init__.py`
- Create: `orchestrator/schemas/common.py`
- Create: `orchestrator/schemas/m1.py`
- Create: `orchestrator/schemas/m2.py`
- Create: `orchestrator/schemas/m3.py`
- Create: `orchestrator/schemas/m4.py`
- Create: `orchestrator/schemas/m5.py`
- Test: `orchestrator/tests/test_schemas.py`

- [ ] **Step 1: Write tests covering all five schemas**

Create `orchestrator/tests/test_schemas.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from orchestrator.schemas.m1 import M1Output
from orchestrator.schemas.m2 import CitedGap, M2Output, PaperReference
from orchestrator.schemas.m3 import M3Output
from orchestrator.schemas.m4 import M4Output
from orchestrator.schemas.m5 import ExportArtifact, M5Output


def test_m1_required_fields():
    out = M1Output(
        research_title="A study on X",
        field="Marketing",
        research_type="quantitative",
        target_population="SME employees",
        scope="Vietnam, 2026",
        objectives=["Identify factors"],
        research_questions=["Does X affect Y?"],
    )
    assert out.confirmed_at is None


def test_m1_rejects_empty_objectives():
    with pytest.raises(ValidationError):
        M1Output(
            research_title="t", field="Marketing", research_type="quantitative",
            target_population="x", scope="y", objectives=[], research_questions=["q"],
        )


def test_m2_with_cited_gap():
    g = CitedGap(
        description="No SME context",
        supporting_papers=[PaperReference(author="Wang", year=2011, page=118)],
        relevance="High",
        confirmed=True,
    )
    out = M2Output(
        research_state_summary="…",
        research_gaps=[g],
        theoretical_framework="TL + EE",
        hypotheses=["H1"],
        literature_review_doc="…",
        citation_list=[{"author": "Wang", "year": 2011}],
    )
    assert out.research_gaps[0].supporting_papers[0].page == 118


def test_m3_paradigm_branch():
    out = M3Output(
        paradigm="qualitative", design="thematic_analysis", tool="manual",
        sampling_strategy="purposive", target_sample_size=12,
    )
    assert out.conceptual_model is None
    assert out.thematic_framework is None  # optional


def test_m4_minimal():
    out = M4Output(
        data_type_detected="SPSS",
        analysis_outline={"sections": ["Descriptive", "Reliability"], "confirmed_by_user": True},
        results={},
        interpretations={},
    )
    assert out.data_type_detected == "SPSS"


def test_m5_export_artifact():
    a = ExportArtifact(kind="docx", uri="s3://bucket/key", size_bytes=12345)
    out = M5Output(
        sections=[{"name": "Ch.1", "text": "..."}],
        export_artifacts=[a],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.export_artifacts[0].uri.startswith("s3://")
```

- [ ] **Step 2: Run (fails — schemas missing)**

Run: `python -m pytest orchestrator/tests/test_schemas.py -v`
Expected: FAIL.

- [ ] **Step 3: Create the schema files**

Create `orchestrator/schemas/__init__.py`:

```python
"""Module output schemas — one Pydantic model per of the 5 research modules."""
from .m1 import M1Output
from .m2 import M2Output, CitedGap, PaperReference
from .m3 import M3Output
from .m4 import M4Output
from .m5 import M5Output, ExportArtifact

__all__ = [
    "M1Output", "M2Output", "M3Output", "M4Output", "M5Output",
    "CitedGap", "PaperReference", "ExportArtifact",
]
```

Create `orchestrator/schemas/common.py`:

```python
"""Enums and shared types used across module schemas."""
from typing import Literal

ResearchType = Literal["quantitative", "qualitative", "mixed"]
Paradigm = Literal["quantitative", "qualitative", "mixed"]
AcademicField = str  # Free-form for sub-project 1; tightens later.
CitationStyle = Literal["apa7", "apa6", "vancouver", "chicago", "harvard", "ieee", "custom"]
Language = Literal["vi", "en", "bilingual"]
```

Create `orchestrator/schemas/m1.py`:

```python
"""M1 Topic Discovery output schema. Mirrors PRD §6.1.3."""
from datetime import datetime
from pydantic import BaseModel, Field

from .common import AcademicField, ResearchType


class M1Output(BaseModel):
    """Confirmed when all required fields filled + user OK'd."""
    research_title: str = Field(..., min_length=1)
    field: AcademicField
    research_type: ResearchType
    target_population: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    objectives: list[str] = Field(..., min_length=1)
    research_questions: list[str] = Field(..., min_length=1)
    confirmed_at: datetime | None = None
```

Create `orchestrator/schemas/m2.py`:

```python
"""M2 Literature Review output schema. Mirrors PRD §6.2.4 + §5.2."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class PaperReference(BaseModel):
    author: str
    year: int
    page: int | None = None
    quote: str | None = None
    verified: bool = False


class CitedGap(BaseModel):
    description: str = Field(..., min_length=1)
    supporting_papers: list[PaperReference] = Field(default_factory=list)
    relevance: Literal["High", "Medium", "Low"] = "Medium"
    confirmed: bool = False


class M2Output(BaseModel):
    research_state_summary: str
    research_gaps: list[CitedGap] = Field(..., min_length=1)
    theoretical_framework: str
    hypotheses: list[str] = Field(default_factory=list)   # quant
    propositions: list[str] = Field(default_factory=list) # qual
    literature_review_doc: str
    citation_list: list[dict]
    confirmed_at: datetime | None = None
```

Create `orchestrator/schemas/m3.py`:

```python
"""M3 Research Design output schema. Mirrors PRD §6.3.6."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from .common import Paradigm


class M3Output(BaseModel):
    paradigm: Paradigm
    design: str = Field(..., description="e.g. PLS-SEM, Thematic Analysis, Sequential Explanatory")
    tool: str = Field(..., description="SmartPLS, NVivo, SPSS, …")
    sampling_strategy: str
    target_sample_size: int = Field(..., gt=0)
    conceptual_model: dict | None = None      # quantitative
    thematic_framework: dict | None = None    # qualitative
    constructs: list[dict] = Field(default_factory=list)
    questionnaire_text: str | None = None
    interview_guide: str | None = None
    confirmed_at: datetime | None = None
```

Create `orchestrator/schemas/m4.py`:

```python
"""M4 Data Analysis output schema. Mirrors PRD §6.4.7."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class M4Output(BaseModel):
    data_type_detected: Literal[
        "SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"
    ]
    analysis_outline: dict
    results: dict
    interpretations: dict
    custom_analyses: list[dict] = Field(default_factory=list)
    confirmed_at: datetime | None = None
```

Create `orchestrator/schemas/m5.py`:

```python
"""M5 Writing & Finalization output schema. Mirrors PRD §6.5."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ExportArtifact(BaseModel):
    kind: Literal["docx", "pdf", "latex", "md"]
    uri: str
    size_bytes: int = Field(..., ge=0)


class M5Output(BaseModel):
    sections: list[dict] = Field(..., min_length=1)  # [{name, text, ...}]
    export_artifacts: list[ExportArtifact] = Field(default_factory=list)
    confirmed_at: datetime | None = None
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/test_schemas.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/schemas/ orchestrator/tests/test_schemas.py
git commit -m "feat(orchestrator): pydantic output schemas for M1-M5"
```

---

## Task 6: Concurrency helper (first-confirm wins on context_store)

**Files:**
- Create: `orchestrator/concurrency.py`
- Test: `orchestrator/tests/test_concurrency.py`

- [ ] **Step 1: Write the test**

Create `orchestrator/tests/test_concurrency.py`:

```python
"""Verifies first-confirm-wins + alert on second commit to same module."""
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore, Project, User
from orchestrator.concurrency import (
    ContextCommitConflict, commit_module_output,
)


def _make_project(db: Session) -> Project:
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
             password_hash="x")
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
    db.add(p); db.flush()
    db.add(ContextStore(project_id=p.id))
    db.commit()
    return p


def test_first_commit_wins_second_raises_conflict():
    with Session(get_engine()) as db:
        p = _make_project(db)

    blob = {"research_title": "X", "objectives": ["a"], "research_questions": ["q"],
            "field": "Marketing", "research_type": "quantitative",
            "target_population": "x", "scope": "y",
            "confirmed_at": datetime.now(timezone.utc).isoformat()}

    # Thread A commits first
    with Session(get_engine()) as db:
        commit_module_output(db, project_id=p.id, module="M1",
                             output=blob, thread_name="Main")
        db.commit()

    # Thread B tries to commit — must raise ContextCommitConflict
    with Session(get_engine()) as db, pytest.raises(ContextCommitConflict) as exc:
        commit_module_output(db, project_id=p.id, module="M1",
                             output={**blob, "research_title": "Y"},
                             thread_name="Alt")
        db.commit()
    assert "Main" in str(exc.value)


def test_unrelated_module_commit_still_succeeds():
    with Session(get_engine()) as db:
        p = _make_project(db)
    blob_m1 = {"confirmed_at": "2026-05-26T00:00:00+00:00", "research_title": "X"}
    blob_m2 = {"confirmed_at": "2026-05-26T00:00:00+00:00", "research_state_summary": "..."}
    with Session(get_engine()) as db:
        commit_module_output(db, project_id=p.id, module="M1",
                             output=blob_m1, thread_name="Main")
        commit_module_output(db, project_id=p.id, module="M2",
                             output=blob_m2, thread_name="Main")
        db.commit()
    with Session(get_engine()) as db:
        cs = db.get(ContextStore, p.id)
        assert cs.m1_topic["research_title"] == "X"
        assert cs.m2_literature["research_state_summary"] == "..."


def test_parallel_commits_only_one_wins(pg_url):
    """Two genuinely parallel sessions racing on M1 — exactly one succeeds."""
    with Session(get_engine()) as db:
        p = _make_project(db)
    results = {"ok": 0, "conflict": 0}
    barrier = threading.Barrier(2)

    def worker(name: str):
        from sqlalchemy import create_engine
        eng = create_engine(pg_url)
        with Session(eng) as db:
            barrier.wait()  # try to align them
            try:
                commit_module_output(
                    db, project_id=p.id, module="M1",
                    output={"confirmed_at": "2026-05-26T00:00:00+00:00", "v": name},
                    thread_name=name,
                )
                db.commit()
                results["ok"] += 1
            except ContextCommitConflict:
                results["conflict"] += 1

    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert results["ok"] == 1
    assert results["conflict"] == 1
```

- [ ] **Step 2: Run (fails — concurrency module missing)**

Run: `python -m pytest orchestrator/tests/test_concurrency.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Write the concurrency helper**

Create `orchestrator/concurrency.py`:

```python
"""First-confirm-wins commit for the project-shared context_store.

Concurrent threads within the same project may both reach the end of the same
module. We use a row-level lock on context_store(project_id) so the second
committer can detect "field X already filled" and raise a structured conflict
that the agent can surface to the user.
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ModuleKey = Literal["M1", "M2", "M3", "M4", "M5"]

_MODULE_COLUMN = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


class ContextCommitConflict(RuntimeError):
    """Raised when a thread tries to confirm a module already confirmed elsewhere."""

    def __init__(self, module: ModuleKey, project_id: UUID,
                 existing_thread_name: str, existing_confirmed_at: str):
        super().__init__(
            f"{module} was already confirmed in thread '{existing_thread_name}' "
            f"at {existing_confirmed_at}"
        )
        self.module = module
        self.project_id = project_id
        self.existing_thread_name = existing_thread_name
        self.existing_confirmed_at = existing_confirmed_at


def commit_module_output(
    db: Session,
    *,
    project_id: UUID,
    module: ModuleKey,
    output: dict,
    thread_name: str,
) -> None:
    """Commit `output` to context_store.<module_column> with first-confirm-wins.

    Caller still owns the transaction (must `db.commit()` after).

    Behavior:
      - SELECT … FOR UPDATE on the context_store row for this project.
      - If the module column is already non-null AND has a confirmed_at value,
        raise ContextCommitConflict with the existing thread's name.
      - Otherwise, write the new JSONB.
    """
    column = _MODULE_COLUMN[module]
    existing = db.execute(
        text(f"SELECT {column} FROM context_store WHERE project_id = :pid FOR UPDATE"),
        {"pid": project_id},
    ).scalar()

    if existing and existing.get("confirmed_at"):
        # Look up who wrote it. We don't store this directly, but we can find
        # the thread that last confirmed the module via its messages.
        # Conservative default: report "another thread" if the trail is gone.
        existing_thread = _find_confirming_thread(db, project_id, module) or "another thread"
        raise ContextCommitConflict(
            module=module,
            project_id=project_id,
            existing_thread_name=existing_thread,
            existing_confirmed_at=existing["confirmed_at"],
        )

    db.execute(
        text(
            f"UPDATE context_store SET {column} = CAST(:val AS JSONB), "
            f"updated_at = NOW() WHERE project_id = :pid"
        ),
        {"val": _json_dumps(output), "pid": project_id},
    )
    # Record provenance so future conflicts can name the source thread.
    db.execute(
        text(
            "INSERT INTO messages (thread_id, role, content, module_tag) "
            "SELECT t.id, 'system', :marker, :module "
            "FROM threads t WHERE t.project_id = :pid AND t.name = :tname "
            "LIMIT 1"
        ),
        {"marker": f"[confirmed {module}]", "module": module,
         "pid": project_id, "tname": thread_name},
    )
    logger.info("context_store.%s committed for project %s by thread %s",
                column, project_id, thread_name)


def _find_confirming_thread(db: Session, project_id: UUID, module: ModuleKey) -> str | None:
    """Look up the thread that emitted the `[confirmed M*]` system message."""
    row = db.execute(
        text(
            "SELECT t.name FROM messages m JOIN threads t ON t.id = m.thread_id "
            "WHERE t.project_id = :pid AND m.module_tag = :module "
            "AND m.content = :marker ORDER BY m.id DESC LIMIT 1"
        ),
        {"pid": project_id, "module": module, "marker": f"[confirmed {module}]"},
    ).scalar()
    return row


def _json_dumps(d: dict) -> str:
    import json
    return json.dumps(d, default=str)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest orchestrator/tests/test_concurrency.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/concurrency.py orchestrator/tests/test_concurrency.py
git commit -m "feat(orchestrator): first-confirm-wins context_store commit helper"
```

---

## Task 7: M1 tools (Topic Discovery)

**Files:**
- Create: `orchestrator/tools/__init__.py`
- Create: `orchestrator/tools/m1_topic.py`
- Test: `orchestrator/tests/test_tools_m1.py`

- [ ] **Step 1: Write the tests**

Create `orchestrator/tests/test_tools_m1.py`:

```python
from orchestrator.tools.m1_topic import suggest_topics, refine_title


class _FakeLLM:
    """Returns deterministic strings — no network call."""
    def __init__(self, response: str):
        self._response = response

    def invoke(self, prompt):
        from langchain_core.messages import AIMessage
        return AIMessage(content=self._response)


def test_suggest_topics_returns_list(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _FakeLLM('["Topic A", "Topic B", "Topic C"]'),
    )
    out = suggest_topics.invoke({"field": "Marketing"})
    assert out == ["Topic A", "Topic B", "Topic C"]


def test_suggest_topics_handles_malformed_response(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _FakeLLM("not json"),
    )
    out = suggest_topics.invoke({"field": "Marketing"})
    assert out == []  # graceful: empty list, not exception


def test_refine_title_passes_seed_to_llm(monkeypatch):
    captured = {}
    class _Capture(_FakeLLM):
        def invoke(self, prompt):
            captured["prompt"] = str(prompt)
            return super().invoke(prompt)
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _Capture("The Impact of X on Y at Z"),
    )
    out = refine_title.invoke({"seed": "X and Y in Vietnam"})
    assert out == "The Impact of X on Y at Z"
    assert "X and Y in Vietnam" in captured["prompt"]
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_tools_m1.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement M1 tools**

Create `orchestrator/tools/__init__.py`:

```python
"""LangChain @tool wrappers exposing engine/* functions and small LLM helpers."""
```

Create `orchestrator/tools/m1_topic.py`:

```python
"""M1 — Topic Discovery tools.

Sub-project 1 ships light LLM helpers; later sub-projects can swap in
domain-specific data sources (Semantic Scholar trending topics, etc.).
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    """Single chokepoint for LLM creation — easy to monkeypatch in tests."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.4,
    )


@tool
def suggest_topics(field: str) -> list[str]:
    """Return 5-10 currently-trending research topics in the given academic field.

    Returns an empty list if the LLM can't produce a JSON-parseable response.
    """
    llm = _get_llm()
    prompt = (
        f"List 5 to 10 currently-trending research topics in the field of {field}. "
        "Respond with ONLY a JSON array of strings, no prose."
    )
    resp = llm.invoke(prompt).content
    try:
        topics = json.loads(resp)
        if isinstance(topics, list):
            return [str(t) for t in topics]
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_topics: malformed LLM response: %r", resp[:200])
    return []


@tool
def refine_title(seed: str) -> str:
    """Polish a draft thesis title into academic phrasing.

    Returns the polished title verbatim from the LLM. Caller should validate.
    """
    llm = _get_llm()
    prompt = (
        f"You are an academic writing coach. Rewrite this draft research title in "
        f"clear, formal academic English. Return ONLY the polished title, no quotes "
        f"or explanation. Draft: {seed}"
    )
    return llm.invoke(prompt).content.strip()
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/test_tools_m1.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/ orchestrator/tests/test_tools_m1.py
git commit -m "feat(orchestrator): M1 topic discovery tools (suggest_topics, refine_title)"
```

---

## Task 8: M2 tools (Literature Review — wrap engine citation pipeline)

**Files:**
- Create: `orchestrator/tools/m2_literature.py`
- Test: `orchestrator/tests/test_tools_m2.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/test_tools_m2.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)


def test_scout_citations_calls_engine_with_min_n(monkeypatch):
    fake_result = {"citations": [
        MagicMock(title="Paper A", authors="Wang", year=2011,
                  source="Journal", url="http://x"),
    ], "count": 1}
    captured = {}
    def fake_research(model, research_topics, output_path, target_minimum, **kw):
        captured["target_minimum"] = target_minimum
        captured["topics"] = research_topics
        return fake_result
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research
    )
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock()
    )

    out = scout_citations.invoke({"topic": "Transformational leadership", "min_n": 30})
    assert captured["target_minimum"] == 30
    assert any("Transformational leadership" in t for t in captured["topics"])
    assert out[0]["title"] == "Paper A"


def test_summarize_paper_reads_file_and_calls_llm(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.txt"
    pdf.write_text("This paper studies X. Key findings: A, B, C.")
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Studies X; finds A, B, C."
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: fake_llm)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._read_paper_text",
        lambda p: pdf.read_text(),
    )
    out = summarize_paper.invoke({"pdf_path": str(pdf)})
    assert out == "Studies X; finds A, B, C."


def test_find_research_gaps_asks_llm_for_json(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        '[{"description":"No SME context","relevance":"High",'
        '"supporting_papers":[{"author":"Wang","year":2011}]}]'
    )
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: fake_llm)
    gaps = find_research_gaps.invoke({
        "citations": [{"title": "X", "author": "Wang", "year": 2011}],
    })
    assert len(gaps) == 1
    assert gaps[0]["description"] == "No SME context"


def test_compile_citations_uses_engine_compiler(monkeypatch):
    fake = MagicMock()
    fake.compile.return_value = "Wang, X. (2011). …"
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.CitationCompiler", lambda style: fake
    )
    out = compile_citations.invoke({
        "items": [{"author": "Wang", "year": 2011, "title": "X"}],
        "style": "apa7",
    })
    assert "Wang" in out


def test_verify_page_numbers_returns_status(monkeypatch):
    out = verify_page_numbers.invoke({
        "claim": {"author": "Wang", "year": 2011, "page": 118, "quote": "leadership inspires"},
    })
    # Sub-project 1: returns "unverified" when we don't have the PDF cached.
    assert out["status"] in {"verified", "unverified", "not_found"}
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_tools_m2.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement M2 tools**

Create `orchestrator/tools/m2_literature.py`:

```python
"""M2 — Literature Review tools.

Thin wrappers around engine/utils/* + small LLM helpers. The heavy lifting
(citation discovery, deep research, citation formatting) stays in engine/.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

# Make engine package importable as a sibling.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Late imports so import-time failures of engine don't crash the orchestrator
# at import time. Each tool function imports lazily.

logger = logging.getLogger(__name__)


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.3,
    )


# Re-exported here so tests can monkeypatch easily.
def research_citations_via_api(model, research_topics, output_path, target_minimum, **kw):
    from engine.utils.agent_runner import research_citations_via_api as _real
    return _real(model, research_topics, output_path, target_minimum, **kw)


def _read_paper_text(p: str) -> str:
    path = Path(p)
    if path.suffix.lower() == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except Exception:
            logger.warning("pdfminer extract failed for %s", path)
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


@tool
def scout_citations(topic: str, min_n: int = 20) -> list[dict]:
    """Discover at least `min_n` academic citations for `topic`.

    Returns a list of dicts: {title, authors, year, source, url, doi}.
    Backed by engine/utils/agent_runner.research_citations_via_api.
    """
    research_topics = [
        f"{topic} fundamentals and background",
        f"{topic} current state of research",
        f"{topic} methodology and approaches",
    ]
    tmp = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    tmp.mkdir(parents=True, exist_ok=True)
    result = research_citations_via_api(
        model=_get_llm(),
        research_topics=research_topics,
        output_path=tmp / "scout_raw.md",
        target_minimum=min_n,
    )
    citations = result.get("citations", [])
    return [
        {
            "title": getattr(c, "title", None) or c.get("title"),
            "authors": getattr(c, "authors", None) or c.get("authors"),
            "year": getattr(c, "year", None) or c.get("year"),
            "source": getattr(c, "source", None) or c.get("source"),
            "url": getattr(c, "url", None) or c.get("url"),
            "doi": getattr(c, "doi", None) or c.get("doi"),
        }
        for c in citations
    ]


@tool
def summarize_paper(pdf_path: str) -> str:
    """Read a PDF / text file and produce a concise academic summary."""
    text = _read_paper_text(pdf_path)
    if not text.strip():
        return ""
    snippet = text[:8000]
    llm = _get_llm()
    prompt = (
        "Summarize this academic paper in 3-5 sentences. Focus on: research question, "
        "method, key findings, theoretical contribution. Plain prose, no headings.\n\n"
        + snippet
    )
    return llm.invoke(prompt).content.strip()


@tool
def find_research_gaps(citations: list[dict]) -> list[dict]:
    """Identify research gaps from a list of citations.

    Returns: [{description, supporting_papers, relevance}, ...]
    Backed by an LLM call (no engine wrapping yet — pure prompt).
    """
    if not citations:
        return []
    cites_block = json.dumps(citations[:50], default=str)[:6000]
    llm = _get_llm()
    prompt = (
        "Analyze these citations and identify 2-4 specific research gaps. "
        "Respond with ONLY a JSON array, no prose. Schema: "
        '[{"description": "...", "relevance": "High|Medium|Low", '
        '"supporting_papers": [{"author": "...", "year": 2020}]}].\n\n'
        f"Citations: {cites_block}"
    )
    resp = llm.invoke(prompt).content
    try:
        return list(json.loads(resp))
    except (json.JSONDecodeError, TypeError):
        logger.warning("find_research_gaps: malformed LLM response: %r", resp[:200])
        return []


# Wrapper class so tests can monkeypatch at the symbol.
class CitationCompiler:
    def __init__(self, style: str):
        from engine.utils.citation_compiler import CitationCompiler as _Real
        self._inner = _Real(style)

    def compile(self, items):
        return self._inner.compile(items)


@tool
def compile_citations(items: list[dict], style: str = "apa7") -> str:
    """Format `items` into a citation list using the given style.

    Backed by engine/utils/citation_compiler.CitationCompiler.
    """
    return CitationCompiler(style).compile(items)


@tool
def verify_page_numbers(claim: dict) -> dict:
    """Verify a page-reference claim against the source PDF if available.

    `claim` shape: {author, year, page, quote, [pdf_path]}.
    Returns: {status: "verified" | "unverified" | "not_found", message: str}.
    Sub-project 1: returns "unverified" when no PDF path; a follow-on sub-project
    will integrate the existing PDF text-search code in engine/utils/.
    """
    pdf_path = claim.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return {"status": "unverified",
                "message": "No source PDF available — page reference marked [page?]"}
    text = _read_paper_text(pdf_path)
    quote = (claim.get("quote") or "").strip()
    if quote and quote.lower() in text.lower():
        return {"status": "verified", "message": "Quote found in source PDF"}
    return {"status": "not_found",
            "message": "Quote not found at the cited page; user should re-check"}
```

- [ ] **Step 4: Run**

Run: `python -m pytest orchestrator/tests/test_tools_m2.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m2_literature.py orchestrator/tests/test_tools_m2.py
git commit -m "feat(orchestrator): M2 literature tools (scout, summarize, gaps, compile, verify)"
```

---

## Task 9: M3 tools (Research Design)

**Files:**
- Create: `orchestrator/tools/m3_design.py`
- Test: `orchestrator/tests/test_tools_m3.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/test_tools_m3.py`:

```python
import json
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m3_design import (
    build_conceptual_model, estimate_sample_size, recommend_methodology,
    suggest_scale_items,
)


def test_recommend_methodology_returns_structured(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "design": "PLS-SEM", "tool": "SmartPLS",
        "rationale": "latent variables + small sample"
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    out = recommend_methodology.invoke({
        "research_question": "Does TL affect EE?",
        "paradigm": "quantitative",
    })
    assert out["design"] == "PLS-SEM"
    assert out["tool"] == "SmartPLS"


def test_build_conceptual_model_returns_constructs_and_paths(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "constructs": ["TL", "EE", "Trust"],
        "paths": [
            {"from": "TL", "to": "EE", "hypothesis": "H1: TL → EE (+)"},
            {"from": "TL", "to": "Trust", "hypothesis": "H2: TL → Trust (+)"},
        ],
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    out = build_conceptual_model.invoke({
        "constructs": ["TL", "EE", "Trust"],
        "research_question": "Does TL affect EE?",
    })
    assert "TL" in out["constructs"]
    assert len(out["paths"]) == 2


def test_suggest_scale_items_returns_items(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"id": "TL1", "text": "My supervisor inspires me with a vision."},
        {"id": "TL2", "text": "My supervisor leads by example."},
    ])
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    items = suggest_scale_items.invoke({"construct": "Transformational Leadership"})
    assert len(items) == 2
    assert items[0]["id"] == "TL1"


def test_estimate_sample_size_quant_pls_sem():
    out = estimate_sample_size.invoke({
        "model": {"design": "PLS-SEM", "n_constructs": 4, "max_arrows_per_construct": 3},
    })
    assert isinstance(out, dict)
    assert out["min_size"] >= 100
    assert out["recommended"] >= out["min_size"]


def test_estimate_sample_size_qualitative():
    out = estimate_sample_size.invoke({
        "model": {"design": "Thematic Analysis"},
    })
    # qualitative gets a smaller saturation-based range.
    assert out["min_size"] <= 30
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_tools_m3.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement M3 tools**

Create `orchestrator/tools/m3_design.py`:

```python
"""M3 — Research Design tools."""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.3,
    )


@tool
def recommend_methodology(research_question: str, paradigm: str) -> dict:
    """Suggest a research design + analysis tool for the given RQ and paradigm.

    Returns: {design, tool, rationale}.
    """
    llm = _get_llm()
    prompt = (
        "Given this research question and paradigm, recommend a specific research "
        "design and primary analysis tool. Respond with ONLY a JSON object: "
        '{"design": "<e.g. PLS-SEM>", "tool": "<e.g. SmartPLS>", '
        '"rationale": "<one sentence>"}.\n\n'
        f"Research question: {research_question}\nParadigm: {paradigm}"
    )
    try:
        return json.loads(llm.invoke(prompt).content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("recommend_methodology: malformed response")
        return {"design": "regression", "tool": "SPSS", "rationale": "fallback default"}


@tool
def build_conceptual_model(constructs: list[str], research_question: str) -> dict:
    """Build a conceptual model with paths between constructs.

    Returns: {constructs, paths: [{from, to, hypothesis}]}.
    """
    llm = _get_llm()
    prompt = (
        "Build a quantitative conceptual model. Given constructs and RQ, return "
        "ONLY a JSON object: "
        '{"constructs": [...], "paths": [{"from":"A","to":"B","hypothesis":"H1: ..."}]}.\n\n'
        f"Constructs: {constructs}\nResearch question: {research_question}"
    )
    try:
        return json.loads(llm.invoke(prompt).content)
    except (json.JSONDecodeError, TypeError):
        return {"constructs": constructs, "paths": []}


@tool
def suggest_scale_items(construct: str, n: int = 5) -> list[dict]:
    """Suggest `n` Likert items measuring the construct.

    Returns: [{id, text}, ...].
    """
    llm = _get_llm()
    prompt = (
        f"Write {n} validated-style Likert items (5-point) measuring the construct "
        f"'{construct}'. Respond with ONLY a JSON array: "
        f'[{{"id": "C1", "text": "..."}}, ...].'
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        return []


@tool
def estimate_sample_size(model: dict) -> dict:
    """Estimate minimum and recommended sample sizes for a given design.

    Returns: {min_size, recommended, rationale}.
    """
    design = (model.get("design") or "").lower()
    if "qualitative" in design or "thematic" in design or "grounded" in design or "case" in design:
        return {"min_size": 8, "recommended": 15,
                "rationale": "Purposive sampling until data saturation (Braun & Clarke, 2006)."}
    if "pls" in design or "sem" in design:
        # 10x rule (Hair et al.): n >= 10 × largest number of indicators or arrows pointing to a construct.
        arrows = int(model.get("max_arrows_per_construct", 3))
        n_min = max(100, 10 * arrows)
        return {"min_size": n_min, "recommended": int(n_min * 1.5),
                "rationale": f"10× max arrows rule (Hair et al., 2019), n_min = 10 × {arrows}."}
    if "regression" in design or "anova" in design:
        return {"min_size": 100, "recommended": 200,
                "rationale": "Cohen (1988) heuristic for medium effect, α=0.05, power=0.8."}
    # Default
    return {"min_size": 150, "recommended": 250, "rationale": "Generic quantitative default."}
```

- [ ] **Step 4: Run**

Run: `python -m pytest orchestrator/tests/test_tools_m3.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m3_design.py orchestrator/tests/test_tools_m3.py
git commit -m "feat(orchestrator): M3 design tools (methodology, conceptual model, scale, sample size)"
```

---

## Task 10: M4 tools (Data Analysis — stubs for sub-project 1)

**Files:**
- Create: `orchestrator/tools/m4_analysis.py`
- Test: `orchestrator/tests/test_tools_m4.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/test_tools_m4.py`:

```python
import pytest

from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline, interpret_result,
    run_analysis_step,
)


def test_detect_data_type_spss_by_extension(tmp_path):
    f = tmp_path / "data.sav"; f.write_bytes(b"\x00")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "SPSS"


def test_detect_data_type_smartpls_by_html_signature(tmp_path):
    f = tmp_path / "report.html"
    f.write_text("<html><body>SmartPLS 4 PLS Algorithm Results — Outer Loadings</body></html>")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "SmartPLS"


def test_detect_data_type_qualitative_text(tmp_path):
    f = tmp_path / "transcript.txt"
    f.write_text("Interviewer: tell me about your experience.\nParticipant: ...")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "Qualitative"


def test_detect_data_type_unknown(tmp_path):
    f = tmp_path / "binary.bin"; f.write_bytes(b"\xff" * 100)
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "Unknown"


def test_generate_analysis_outline_spss():
    out = generate_analysis_outline.invoke({
        "data_type": "SPSS", "methodology": {"design": "Regression"},
    })
    assert "sections" in out
    assert any("descriptive" in s.lower() for s in out["sections"])


def test_generate_analysis_outline_smartpls():
    out = generate_analysis_outline.invoke({
        "data_type": "SmartPLS", "methodology": {"design": "PLS-SEM"},
    })
    assert any("htmt" in s.lower() or "loadings" in s.lower() for s in out["sections"])


def test_run_analysis_step_returns_stub():
    # Sub-project 1: stub returns the step name + a placeholder result.
    out = run_analysis_step.invoke({
        "step_name": "Cronbach's Alpha", "data": {"alpha": 0.84},
    })
    assert out["step"] == "Cronbach's Alpha"
    assert "summary" in out


def test_interpret_result_in_vietnamese():
    out = interpret_result.invoke({
        "result": {"alpha": 0.84}, "language": "vi",
    })
    assert isinstance(out, str)
    assert len(out) > 0
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_tools_m4.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement M4 tools**

Create `orchestrator/tools/m4_analysis.py`:

```python
"""M4 — Data Analysis tools.

Sub-project 1 ships file-type detection + outline generation as real logic,
but `run_analysis_step` and `interpret_result` are LLM-based stubs. A later
sub-project will replace them with proper SPSS/SmartPLS/CB-SEM parsers.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

DataType = Literal["SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"]

_SPSS_EXTS = {".sav", ".spv", ".sps"}
_SEM_HTML_MARKERS = ("smartpls", "pls algorithm", "outer loadings", "htmt", "amos output", "lavaan")


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.2,
    )


@tool
def detect_data_type(file_path: str) -> DataType:
    """Identify which analysis software / paradigm produced this file.

    Detection priority:
      1. file extension (.sav/.spv/.sps → SPSS)
      2. HTML signature (SmartPLS / AMOS / lavaan keywords)
      3. plain-text heuristic (interview transcript)
      4. Unknown
    """
    p = Path(file_path)
    if not p.exists():
        return "Unknown"
    if p.suffix.lower() in _SPSS_EXTS:
        return "SPSS"
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:8000].lower()
    except Exception:
        return "Unknown"
    for marker in _SEM_HTML_MARKERS:
        if marker in head:
            if "smartpls" in head or "pls algorithm" in head or "htmt" in head:
                return "SmartPLS"
            return "CB-SEM"
    if "interviewer:" in head or "participant:" in head or "p1:" in head:
        return "Qualitative"
    return "Unknown"


_OUTLINE_TEMPLATES: dict[str, list[str]] = {
    "SPSS": [
        "Descriptive Statistics", "Reliability (Cronbach's Alpha)",
        "EFA", "Correlation Matrix", "Regression Analysis", "ANOVA / t-tests",
    ],
    "SmartPLS": [
        "Measurement Model: Outer Loadings",
        "Convergent Validity: AVE & CR",
        "Discriminant Validity: HTMT & Fornell-Larcker",
        "Collinearity: VIF",
        "Path Coefficients (Bootstrap 5000)",
        "R² and Adjusted R²",
        "Effect size (f²)",
        "Predictive Relevance (Q²)",
    ],
    "CB-SEM": [
        "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
        "Discriminant Validity",
        "Structural Model",
        "Mediation/Moderation",
    ],
    "Qualitative": [
        "Familiarization with data",
        "Initial coding (line-by-line)",
        "Theme generation",
        "Theme review & refinement",
        "Theme definition & naming",
        "Writing results with verbatim quotes",
    ],
    "Mixed": ["Quantitative phase (see SPSS/SmartPLS outline)",
              "Qualitative phase (Thematic Analysis)",
              "Integration: convergence, divergence, expansion"],
}


@tool
def generate_analysis_outline(data_type: str, methodology: dict | None = None) -> dict:
    """Return a standard analysis outline for the given data type."""
    sections = list(_OUTLINE_TEMPLATES.get(data_type, ["Generic descriptive", "Generic inferential"]))
    return {"sections": sections, "data_type": data_type, "confirmed_by_user": False}


@tool
def run_analysis_step(step_name: str, data: dict) -> dict:
    """Sub-project 1 stub: returns a placeholder result for the named step.

    A later sub-project will replace this with real SPSS/SmartPLS parsing.
    """
    return {"step": step_name, "summary": f"Stub result for {step_name}", "raw": data}


@tool
def interpret_result(result: dict, language: str = "en") -> str:
    """Plain-language interpretation of a statistical result.

    `language` ∈ {"en", "vi"}.
    """
    llm = _get_llm()
    prompt = (
        f"Interpret this statistical result in academic prose (1-2 short paragraphs). "
        f"Language: {'Vietnamese' if language == 'vi' else 'English'}. "
        f"Mention thresholds where relevant.\n\nResult: {json.dumps(result, default=str)}"
    )
    return llm.invoke(prompt).content.strip()
```

- [ ] **Step 4: Run**

Run: `python -m pytest orchestrator/tests/test_tools_m4.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m4_analysis.py orchestrator/tests/test_tools_m4.py
git commit -m "feat(orchestrator): M4 analysis tools (detect type, outline, step stub, interpret)"
```

---

## Task 11: M5 tools (Writing — wrap engine compose + compile pipeline)

**Files:**
- Create: `orchestrator/tools/m5_writing.py`
- Test: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/test_tools_m5.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m5_writing import (
    compile_pdf, compose_section, export_docx, format_citations, validate_draft,
)


def test_compose_section_uses_engine_compose(monkeypatch):
    fake_compose = MagicMock(return_value="Chapter 2: Literature Review draft...")
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._compose_section_via_engine", fake_compose
    )
    out = compose_section.invoke({
        "section_name": "lit_review",
        "context_store": {
            "m1_topic": {"research_title": "X"},
            "m2_literature": {"research_gaps": [{"description": "..."}]},
        },
    })
    assert "Chapter" in out
    fake_compose.assert_called_once()


def test_validate_draft_returns_ok_when_no_issues(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._validate_via_engine",
        lambda text: {"issues": [], "score": 0.95},
    )
    out = validate_draft.invoke({"text": "This is the draft."})
    assert out["score"] == 0.95
    assert out["issues"] == []


def test_compile_pdf_writes_artifact(tmp_path, monkeypatch):
    captured = {}
    def fake_compile(sections, output_path, **kw):
        captured["sections"] = sections
        captured["output_path"] = output_path
        Path(output_path).write_bytes(b"%PDF-1.4 fake")
        return output_path
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._compile_pdf_via_engine", fake_compile
    )
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = compile_pdf.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
    })
    assert out.endswith(".pdf")
    assert Path(out).exists()


def test_export_docx_writes_artifact(tmp_path, monkeypatch):
    def fake_docx(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 docx fake")
        return output_path
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._export_docx_via_engine", fake_docx
    )
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))
    out = export_docx.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
    })
    assert out.endswith(".docx")
    assert Path(out).exists()


def test_format_citations_apa(monkeypatch):
    fake = MagicMock()
    fake.compile.return_value = "Wang, X. (2011). Title."
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing.CitationCompiler", lambda style: fake
    )
    out = format_citations.invoke({
        "items": [{"author": "Wang", "year": 2011, "title": "Title"}],
        "style": "apa7",
    })
    assert "Wang" in out
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_tools_m5.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement M5 tools**

Create `orchestrator/tools/m5_writing.py`:

```python
"""M5 — Writing & Export tools.

These tools are the bridge that lets the auto-mode orchestrator produce
the same final artifacts (docx + pdf) that today's `python -m engine` ships.
They delegate into engine/phases/compose, engine/phases/compile, and
engine/utils/* so we don't reimplement the layout/formatting logic.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool

# Make engine package importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _scratch_dir() -> Path:
    d = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# Wrappers — tests monkeypatch these so unit tests stay offline.

def _compose_section_via_engine(section_name: str, context_store: dict) -> str:
    """Compose one section using engine/phases/compose helpers.

    The engine expects a `DraftContext`; we synthesize a minimal one from
    context_store. Heavy lifting (research, structure) is skipped — those
    happened in M1-M4.
    """
    from engine.phases.context import DraftContext

    ctx = DraftContext()
    ctx.topic = (context_store.get("m1_topic") or {}).get("research_title", "Untitled")
    ctx.language = (context_store.get("m1_topic") or {}).get("language", "en")
    # Inject prior outputs as ctx fields the engine compose functions read.
    ctx.scribe_output = (context_store.get("m2_literature") or {}).get("literature_review_doc", "")
    ctx.signal_output = "\n".join(
        g.get("description", "") for g in (context_store.get("m2_literature") or {}).get("research_gaps", [])
    )
    # Compose only the requested section. Each section composer in engine/phases/compose.py
    # accepts a ctx and returns a string.
    from engine.phases import compose as _compose
    composer = {
        "intro":         _compose._compose_intro,
        "lit_review":    _compose._compose_lit_review,
        "methodology":   _compose._compose_methodology,
        "results":       _compose._compose_results,
        "discussion":    _compose._compose_discussion,
        "conclusion":    _compose._compose_conclusion,
    }.get(section_name)
    if composer is None:
        return ""
    return composer(ctx)


def _validate_via_engine(text: str) -> dict:
    from engine.phases.validate import quick_validate
    return quick_validate(text)


def _compile_pdf_via_engine(sections: list[dict], output_path: str, **kw) -> str:
    from engine.utils.export_professional import export_pdf
    return export_pdf(sections, output_path, **kw)


def _export_docx_via_engine(sections: list[dict], output_path: str, **kw) -> str:
    from engine.utils.docx_post_processor import export_docx
    return export_docx(sections, output_path, **kw)


class CitationCompiler:
    def __init__(self, style: str):
        from engine.utils.citation_compiler import CitationCompiler as _Real
        self._inner = _Real(style)

    def compile(self, items):
        return self._inner.compile(items)


@tool
def compose_section(section_name: str, context_store: dict) -> str:
    """Compose one section of the thesis from the project's context_store.

    `section_name` ∈ {"intro", "lit_review", "methodology", "results",
                      "discussion", "conclusion"}.
    Delegates to engine/phases/compose.
    """
    return _compose_section_via_engine(section_name, context_store)


@tool
def validate_draft(text: str) -> dict:
    """Run engine's validation pipeline on a draft section. Returns issues + score."""
    return _validate_via_engine(text)


@tool
def compile_pdf(sections: list[dict]) -> str:
    """Render sections into a PDF artifact, return absolute path."""
    out = _scratch_dir() / f"thesis-{uuid4().hex[:8]}.pdf"
    return _compile_pdf_via_engine(sections, str(out))


@tool
def export_docx(sections: list[dict]) -> str:
    """Render sections into a .docx artifact, return absolute path."""
    out = _scratch_dir() / f"thesis-{uuid4().hex[:8]}.docx"
    return _export_docx_via_engine(sections, str(out))


@tool
def format_citations(items: list[dict], style: str = "apa7") -> str:
    """Format a citation list using the requested style. Delegates to engine."""
    return CitationCompiler(style).compile(items)
```

- [ ] **Step 4: Run**

Run: `python -m pytest orchestrator/tests/test_tools_m5.py -v`
Expected: PASS (5 tests).

> **Note:** If `engine/phases/compose.py` does not have private `_compose_<name>` helpers, the integration tests in Task 28 will catch it and you'll add façade functions to engine/phases/compose.py. The unit tests above pass because they monkeypatch the wrapper.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): M5 writing tools (compose, validate, pdf, docx, citations)"
```

---

End of Phase 0–2 (Tasks 1–11). Continue to `2026-05-26-orchestration-foundation-plan-phase-3-4.md` for Tasks 12–19 (Agents + Graph).
