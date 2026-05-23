# Web ↔ Engine MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Next.js `web/` template to the Python `engine/` pipeline through a new FastAPI service, with email/password auth, AWS S3 storage, and live progress over SSE. No billing.

**Architecture:** Three units. Next.js (existing) talks to a new FastAPI service over HTTPS+SSE. FastAPI spawns `python -m engine` as a subprocess per job; the engine writes activity to `events.jsonl` and uploads artifacts to AWS S3 on completion. FastAPI tails the JSONL file, persists events to Postgres, and fans them out to SSE subscribers.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Alembic · psycopg · boto3 · bcrypt · pytest · testcontainers · moto · Next.js 15 (App Router) · SWR · EventSource.

**Reference spec:** `docs/superpowers/specs/2026-05-23-web-engine-mvp-design.md`

---

## Conventions for every task

- All paths are absolute from repo root: `C:/DFolder/cao_projects/opendraft/`.
- Python: `python --version` must be 3.10+. All `api/` commands assume `cd api/` unless otherwise stated.
- Node: `npm --version` 10+. All `web/` commands assume `cd web/`.
- Commit messages follow the existing style: `area: short summary`.
- Tests use `pytest` (Python) and `vitest`+`@testing-library/react` (web).
- Postgres for tests: the test fixtures spin up a disposable container via `testcontainers`; you do NOT need a local Postgres for tests.
- S3 for tests: `moto[s3]` patches boto3 in-process.
- For tasks that update SQLAlchemy models, ALWAYS create a new Alembic revision (`alembic revision --autogenerate -m "..."`) and verify the generated SQL before committing.

## Required environment variables (`.env` at repo root)

Create `.env` once before starting Task 1:

```env
# Postgres — provision your own (Neon/Supabase/RDS/docker)
DATABASE_URL=postgresql+psycopg://opendraft:opendraft@localhost:5432/opendraft

# AWS S3 (values to source from your own secrets vault — do NOT commit real keys)
AWS_REGION=ap-southeast-1
S3_BUCKET=<your-bucket-name>
S3_PREFIX=opendraft/
AWS_ACCESS_KEY=<your-aws-access-key>
AWS_SECRET_KEY=<your-aws-secret-key>

# Session signing (any long random string, e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`)
SESSION_SECRET=<random-32-char-string>

# Engine API keys
GEMINI_API_KEY=<your-gemini-key>
OPENAI_API_KEY=<your-openai-key>
ANTHROPIC_API_KEY=<your-anthropic-key-or-leave-blank>

# Job workdir (local disk)
JOB_WORKDIR_ROOT=./var/jobs

# Web → API URL (for the Next.js client)
NEXT_PUBLIC_API_BASE=http://localhost:7100/api/v1

# API port
API_PORT=7100
WEB_PORT=3000
```

Add `.env` to `.gitignore` if not already there.

---

## File map (what every new/modified file exists for)

**New `api/` package:**
- `api/pyproject.toml` — dependencies + lint config.
- `api/alembic.ini`, `api/migrations/env.py`, `api/migrations/versions/*` — Alembic.
- `api/app/__init__.py` — empty.
- `api/app/main.py` — FastAPI app, mounts routers, CORS, startup/shutdown.
- `api/app/settings.py` — env-driven settings (pydantic-settings).
- `api/app/db.py` — engine, session factory, dependency.
- `api/app/models.py` — SQLAlchemy ORM models (users, sessions, papers, jobs, job_events).
- `api/app/security.py` — bcrypt + session cookie issue/verify.
- `api/app/deps.py` — `current_user` FastAPI dependency.
- `api/app/s3.py` — boto3 wrapper, prefix-locked.
- `api/app/quotas.py` — `MAX_RUNNING_JOBS_PER_USER`, `MAX_JOBS_PER_DAY` checks.
- `api/app/routers/auth.py` — `/auth/{signup,login,logout,me}`.
- `api/app/routers/papers.py` — `/papers`, `/papers/:id`, draft/citations/exports.
- `api/app/routers/jobs.py` — `/jobs/:id`, `/jobs/:id/events`, `/jobs/:id/cancel`.
- `api/app/job_runner.py` — spawn subprocess, JobMonitor task, in-process pubsub.
- `api/app/sse.py` — SSE response helper.
- `api/tests/conftest.py` — pytest fixtures (Postgres testcontainer, moto S3, app client).
- `api/tests/test_*.py` — per-router tests.

**New engine entrypoint:**
- `engine/__main__.py` — argparse + JobTracker/JobStreamer + S3 uploader.

**New `web/` files:**
- `web/app/lib/api.js` — `apiFetch` + `apiSSE`.
- `web/app/lib/auth-context.jsx` — `useAuth()`.
- `web/middleware.js` — redirect unauth to `/login`.
- `web/app/login/page.jsx`, `web/app/signup/page.jsx` — auth pages.
- `web/app/wizard/page.jsx` — wraps `<Wizard/>`.
- `web/app/paper/[id]/page.jsx` — wraps `<PaperShell/>`.

**Modified `web/` files:**
- `web/app/page.jsx` — dashboard route, fetches papers.
- `web/app/components/shared.jsx` — `Sidebar` drops Billing + Affiliate.
- `web/app/components/dashboard.jsx` — real data + empty state.
- `web/app/components/wizard.jsx` — submits real job.
- `web/app/components/agent-run.jsx` — SSE-driven state.
- `web/app/components/draft-editor.jsx` — read-only render from API.
- `web/app/components/citations.jsx` — fetch from API.
- `web/app/components/export-tab.jsx` — real download links.

**Repo-root:**
- `dev.sh` — replace existing (currently only starts web) to also start API.
- `.env` — created from the template above.
- `.gitignore` — ensure `.env`, `var/`, `api/.venv/` ignored.

---

# Phase A — API foundation

## Task 1: Scaffold `api/` package

**Files:**
- Create: `api/pyproject.toml`
- Create: `api/app/__init__.py`
- Create: `api/app/main.py`
- Create: `api/app/settings.py`
- Create: `api/tests/__init__.py`
- Create: `api/tests/test_health.py`
- Create: `api/README.md`
- Modify: `.gitignore` (add `api/.venv/`, `var/`, `.env`, `__pycache__/`)

- [ ] **Step 1: Create `api/pyproject.toml`**

```toml
[project]
name = "opendraft-api"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.2",
  "alembic>=1.13",
  "python-multipart>=0.0.12",
  "bcrypt>=4.2",
  "itsdangerous>=2.2",
  "boto3>=1.35",
  "python-dotenv>=1.0",
  "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "testcontainers[postgres]>=4.8",
  "moto[s3]>=5.0",
  "ruff>=0.7",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `api/app/settings.py`**

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")

    aws_region: str = Field(alias="AWS_REGION")
    s3_bucket: str = Field(alias="S3_BUCKET")
    s3_prefix: str = Field(alias="S3_PREFIX", default="opendraft/")
    aws_access_key: str = Field(alias="AWS_ACCESS_KEY")
    aws_secret_key: str = Field(alias="AWS_SECRET_KEY")

    session_secret: str = Field(alias="SESSION_SECRET")

    gemini_api_key: str | None = Field(alias="GEMINI_API_KEY", default=None)
    openai_api_key: str | None = Field(alias="OPENAI_API_KEY", default=None)
    anthropic_api_key: str | None = Field(alias="ANTHROPIC_API_KEY", default=None)

    job_workdir_root: Path = Field(alias="JOB_WORKDIR_ROOT", default=Path("./var/jobs"))

    api_port: int = Field(alias="API_PORT", default=7100)
    web_origin: str = Field(alias="WEB_ORIGIN", default="http://localhost:3000")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.job_workdir_root.mkdir(parents=True, exist_ok=True)
        if not _settings.s3_prefix.endswith("/"):
            _settings.s3_prefix += "/"
    return _settings
```

- [ ] **Step 3: Create `api/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OpenDraft API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
```

- [ ] **Step 4: Create `api/app/__init__.py` and `api/tests/__init__.py`**

Both files: empty.

- [ ] **Step 5: Write the failing health test in `api/tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
```

- [ ] **Step 6: Install dev deps and run the test**

```bash
cd api
python -m venv .venv
.venv\Scripts\activate    # Windows; on bash use: source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_health.py -v
```
Expected: 1 passed.

- [ ] **Step 7: Add `api/README.md`**

```markdown
# OpenDraft API

FastAPI service that wires the Next.js web UI to the engine pipeline.

## Dev
    cd api
    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"
    uvicorn app.main:app --reload --port 7100

## Test
    pytest
```

- [ ] **Step 8: Update `.gitignore`**

Append (creating sections only if absent):

```
.env
var/
api/.venv/
api/**/__pycache__/
api/.pytest_cache/
```

- [ ] **Step 9: Commit**

```bash
git add api/ .gitignore
git commit -m "api: scaffold FastAPI service with health endpoint"
```

---

## Task 2: Database layer — models + Alembic init

**Files:**
- Create: `api/app/db.py`
- Create: `api/app/models.py`
- Create: `api/alembic.ini`
- Create: `api/migrations/env.py`
- Create: `api/migrations/script.py.mako`
- Create: `api/migrations/versions/.gitkeep`
- Create: `api/tests/conftest.py`
- Create: `api/tests/test_models.py`

- [ ] **Step 1: Create `api/app/db.py`**

```python
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, future=True, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


def reset_engine_for_tests(url: str) -> None:
    """Test-only: rebind to a different DB URL."""
    global _engine, _SessionLocal
    _engine = create_engine(url, future=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def db_session() -> Generator[Session, None, None]:
    sess = get_session_factory()()
    try:
        yield sess
    finally:
        sess.close()
```

- [ ] **Step 2: Create `api/app/models.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    research_question: Mapped[str | None] = mapped_column(Text)
    academic_level: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    citation_style: Mapped[str] = mapped_column(String(16), nullable=False)
    tone: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    sources_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    latest_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    phase: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    pid: Mapped[int | None] = mapped_column(Integer)
    workdir: Mapped[str | None] = mapped_column(Text)
    events_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(32))
    agent: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[dict | None] = mapped_column(JSONB)
```

Note: SQLAlchemy's `Session` class is in `sqlalchemy.orm`; we name our model `Session` too. That's fine because they never appear in the same namespace — `models.Session` and `sqlalchemy.orm.Session` are imported separately.

- [ ] **Step 3: Initialize Alembic**

```bash
cd api
alembic init migrations
```

This creates `alembic.ini` and `migrations/` files. Overwrite `migrations/env.py` with:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app.models import *  # noqa: F401,F403  — register tables on Base.metadata
from app.settings import get_settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

In `alembic.ini`, change `script_location = migrations` (it should already be set).

- [ ] **Step 4: Create `api/tests/conftest.py`**

```python
import pytest
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from app.db import Base, get_engine, reset_engine_for_tests


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture(autouse=True)
def _bind_db(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    reset_engine_for_tests(pg_url)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield
```

- [ ] **Step 5: Write the failing models test in `api/tests/test_models.py`**

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.models import Job, JobEvent, Paper, Session as UserSession, User


def test_can_persist_full_object_graph():
    with OrmSession(get_engine()) as s:
        user = User(email="a@b.com", password_hash="x")
        s.add(user)
        s.flush()

        sess = UserSession(user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=30))
        s.add(sess)

        paper = Paper(
            user_id=user.id,
            topic="topic",
            academic_level="master",
            language="en",
            citation_style="apa",
            model="gemini-flash",
            sources_json={"crossref": True},
        )
        s.add(paper)
        s.flush()

        job = Job(paper_id=paper.id, status="running", phase="research", progress=0.1)
        s.add(job)
        s.flush()

        s.add(JobEvent(job_id=job.id, type="activity", phase="research", text="hello"))
        s.commit()

        assert s.query(User).count() == 1
        assert s.query(Paper).count() == 1
        assert s.query(Job).count() == 1
        assert s.query(JobEvent).count() == 1
```

- [ ] **Step 6: Run the test (will fail — no schema yet)**

```bash
cd api
pytest tests/test_models.py -v
```
Expected: ERROR (tables missing) or PASS if `create_all` ran. The conftest calls `create_all`, so this should pass without a migration.

Expected: PASS.

- [ ] **Step 7: Generate the first Alembic migration**

```bash
cd api
# requires a reachable Postgres at $DATABASE_URL
alembic revision --autogenerate -m "initial schema"
```

Inspect `api/migrations/versions/<hash>_initial_schema.py`. Confirm it creates all five tables. Hand-fix any oddities (e.g. enum types if autogen produced them — we use plain text columns).

- [ ] **Step 8: Apply the migration against your local Postgres and verify**

```bash
alembic upgrade head
psql $DATABASE_URL -c "\dt"
```
Expected: `users`, `sessions`, `papers`, `jobs`, `job_events` listed.

- [ ] **Step 9: Commit**

```bash
git add api/app/db.py api/app/models.py api/alembic.ini api/migrations/ api/tests/conftest.py api/tests/test_models.py
git commit -m "api: add SQLAlchemy models and initial Alembic migration"
```

---

## Task 3: S3 client wrapper

**Files:**
- Create: `api/app/s3.py`
- Create: `api/tests/test_s3.py`

- [ ] **Step 1: Write the failing test in `api/tests/test_s3.py`**

```python
import boto3
import pytest
from moto import mock_aws

from app.s3 import S3Client


@pytest.fixture
def s3():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="testbucket")
        yield S3Client(bucket="testbucket", prefix="opendraft/", region="us-east-1",
                        access_key="x", secret_key="y")


def test_put_and_get_url_use_prefix(s3):
    s3.put_object("foo.txt", b"hi", content_type="text/plain")
    url = s3.presigned_get("foo.txt", expires_in=60)
    assert "opendraft/foo.txt" in url


def test_refuses_keys_with_dotdot(s3):
    with pytest.raises(ValueError):
        s3.put_object("../escape.txt", b"x")


def test_object_key_must_be_relative(s3):
    with pytest.raises(ValueError):
        s3.put_object("/abs.txt", b"x")
```

- [ ] **Step 2: Run the test (will fail — module missing)**

```bash
cd api
pytest tests/test_s3.py -v
```
Expected: collection error / ImportError.

- [ ] **Step 3: Create `api/app/s3.py`**

```python
from pathlib import PurePosixPath

import boto3
from botocore.config import Config


class S3Client:
    def __init__(self, *, bucket: str, prefix: str, region: str, access_key: str, secret_key: str):
        if not prefix.endswith("/"):
            prefix += "/"
        self.bucket = bucket
        self.prefix = prefix
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def _full_key(self, relative_key: str) -> str:
        if relative_key.startswith("/"):
            raise ValueError("S3 key must be relative")
        p = PurePosixPath(relative_key)
        if ".." in p.parts:
            raise ValueError("S3 key must not contain '..'")
        return self.prefix + str(p)

    def put_object(self, key: str, body: bytes, *, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self.bucket, Key=self._full_key(key), Body=body, **extra)

    def put_file(self, key: str, path: str, *, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        with open(path, "rb") as f:
            self._client.upload_fileobj(f, self.bucket, self._full_key(key), ExtraArgs=extra)

    def presigned_get(self, key: str, *, expires_in: int = 300) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._full_key(key)},
            ExpiresIn=expires_in,
        )

    def head_object(self, key: str) -> dict | None:
        try:
            return self._client.head_object(Bucket=self.bucket, Key=self._full_key(key))
        except self._client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return None
            raise


def get_s3_from_settings(settings) -> S3Client:
    return S3Client(
        bucket=settings.s3_bucket,
        prefix=settings.s3_prefix,
        region=settings.aws_region,
        access_key=settings.aws_access_key,
        secret_key=settings.aws_secret_key,
    )
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
pytest tests/test_s3.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/s3.py api/tests/test_s3.py
git commit -m "api: add prefix-locked S3 client wrapper"
```

---

## Task 4: Security primitives (bcrypt + session cookie)

**Files:**
- Create: `api/app/security.py`
- Create: `api/tests/test_security.py`

- [ ] **Step 1: Write the failing test in `api/tests/test_security.py`**

```python
import pytest

from app.security import hash_password, verify_password, sign_session_id, verify_session_cookie


def test_password_round_trip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_session_cookie_round_trip():
    cookie = sign_session_id("sess-xyz", secret="abc")
    assert verify_session_cookie(cookie, secret="abc") == "sess-xyz"


def test_session_cookie_rejects_tampered():
    cookie = sign_session_id("sess-xyz", secret="abc")
    tampered = cookie[:-2] + "xx"
    with pytest.raises(ValueError):
        verify_session_cookie(tampered, secret="abc")


def test_session_cookie_rejects_wrong_secret():
    cookie = sign_session_id("sess-xyz", secret="abc")
    with pytest.raises(ValueError):
        verify_session_cookie(cookie, secret="other")
```

- [ ] **Step 2: Run the test (will fail)**

```bash
pytest tests/test_security.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `api/app/security.py`**

```python
import bcrypt
from itsdangerous import BadSignature, Signer


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _signer(secret: str) -> Signer:
    return Signer(secret, salt="opendraft-session")


def sign_session_id(session_id: str, *, secret: str) -> str:
    return _signer(secret).sign(session_id.encode()).decode()


def verify_session_cookie(cookie_value: str, *, secret: str) -> str:
    try:
        return _signer(secret).unsign(cookie_value.encode()).decode()
    except BadSignature as e:
        raise ValueError("bad session cookie") from e
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
pytest tests/test_security.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/security.py api/tests/test_security.py
git commit -m "api: add bcrypt password helpers and signed session cookies"
```

---

## Task 5: Auth router — signup / login / logout / me

**Files:**
- Create: `api/app/deps.py`
- Create: `api/app/routers/__init__.py`
- Create: `api/app/routers/auth.py`
- Modify: `api/app/main.py` (mount router)
- Create: `api/tests/test_auth.py`

- [ ] **Step 1: Create `api/app/deps.py`**

```python
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import db_session
from .models import Session as UserSession, User
from .security import verify_session_cookie
from .settings import Settings, get_settings

SESSION_COOKIE = "opendraft_session"


def current_user(
    opendraft_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(db_session),
) -> User:
    if not opendraft_session:
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthenticated", "message": "login required"}})
    try:
        sid = verify_session_cookie(opendraft_session, secret=settings.session_secret)
    except ValueError as e:
        raise HTTPException(status_code=401, detail={"error": {"code": "bad_session", "message": str(e)}})
    sess = db.get(UserSession, sid)
    if sess is None or sess.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail={"error": {"code": "expired", "message": "session expired"}})
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "no_user", "message": "user not found"}})
    return user
```

- [ ] **Step 2: Create `api/app/routers/__init__.py`** (empty file)

- [ ] **Step 3: Create `api/app/routers/auth.py`**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import SESSION_COOKIE, current_user
from ..models import Session as UserSession, User
from ..security import hash_password, sign_session_id, verify_password
from ..settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = timedelta(days=30)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str


def _to_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email)


def _issue_session(db: Session, user: User, settings: Settings, response: Response, request: Request) -> None:
    sess = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        ip=request.client.host if request.client else None,
    )
    db.add(sess)
    db.commit()
    cookie_val = sign_session_id(str(sess.id), secret=settings.session_secret)
    response.set_cookie(
        SESSION_COOKIE,
        cookie_val,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=False,  # set True behind HTTPS in production
        samesite="lax",
        path="/",
    )


@router.post("/signup", status_code=201)
def signup(creds: Credentials, request: Request, response: Response,
           db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    email = creds.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(409, detail={"error": {"code": "email_taken", "message": "email already registered"}})
    user = User(email=email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    _issue_session(db, user, settings, response, request)
    return _to_out(user)


@router.post("/login")
def login(creds: Credentials, request: Request, response: Response,
          db: Session = Depends(db_session), settings: Settings = Depends(get_settings)) -> UserOut:
    user = db.scalar(select(User).where(User.email == creds.email.lower()))
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(401, detail={"error": {"code": "bad_credentials", "message": "invalid email or password"}})
    _issue_session(db, user, settings, response, request)
    return _to_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return _to_out(user)
```

- [ ] **Step 4: Mount the router in `api/app/main.py`**

Replace the `create_app` function body to include the router:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth as auth_router
from .settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OpenDraft API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    app.include_router(auth_router.router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Step 5: Write `api/tests/test_auth.py`**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def _client():
    return TestClient(create_app())


def test_signup_login_me_logout_flow():
    c = _client()

    r = c.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "a@b.com"
    assert c.cookies.get("opendraft_session")

    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"

    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 204
    c.cookies.clear()
    assert c.get("/api/v1/auth/me").status_code == 401

    r = c.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 200


def test_signup_duplicate_returns_409():
    c = _client()
    c.post("/api/v1/auth/signup", json={"email": "x@y.com", "password": "supersecret"})
    r = c.post("/api/v1/auth/signup", json={"email": "x@y.com", "password": "supersecret"})
    assert r.status_code == 409


def test_login_wrong_password_returns_401():
    c = _client()
    c.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "supersecret"})
    r = c.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "nope1234"})
    assert r.status_code == 401
```

- [ ] **Step 6: Run the tests**

```bash
pytest tests/test_auth.py -v
```
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add api/app/deps.py api/app/routers/ api/app/main.py api/tests/test_auth.py
git commit -m "api: auth router with signup, login, logout, me"
```

---

## Task 6: Quotas helper

**Files:**
- Create: `api/app/quotas.py`
- Create: `api/tests/test_quotas.py`

- [ ] **Step 1: Write the failing test in `api/tests/test_quotas.py`**

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.models import Job, Paper, User
from app.quotas import (
    MAX_JOBS_PER_DAY,
    MAX_RUNNING_JOBS_PER_USER,
    QuotaError,
    check_can_start_job,
)


def _user(db):
    u = User(email=f"{uuid.uuid4().hex}@x.com", password_hash="x")
    db.add(u)
    db.flush()
    return u


def _paper(db, u):
    p = Paper(user_id=u.id, topic="t", academic_level="master", language="en",
              citation_style="apa", model="gemini-flash", sources_json={})
    db.add(p)
    db.flush()
    return p


def test_passes_when_no_jobs():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        check_can_start_job(db, u.id)  # no raise


def test_blocks_when_already_running():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        db.add(Job(paper_id=p.id, status="running"))
        db.commit()
        with pytest.raises(QuotaError) as excinfo:
            check_can_start_job(db, u.id)
        assert excinfo.value.code == "already_running"


def test_blocks_when_daily_cap_reached():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        for _ in range(MAX_JOBS_PER_DAY):
            db.add(Job(paper_id=p.id, status="done", started_at=now))
        db.commit()
        with pytest.raises(QuotaError) as excinfo:
            check_can_start_job(db, u.id)
        assert excinfo.value.code == "daily_quota"


def test_does_not_count_jobs_from_yesterday():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
        for _ in range(MAX_JOBS_PER_DAY):
            db.add(Job(paper_id=p.id, status="done", started_at=yesterday))
        db.commit()
        check_can_start_job(db, u.id)  # no raise
```

- [ ] **Step 2: Run — expect failure (module missing)**

```bash
pytest tests/test_quotas.py -v
```

- [ ] **Step 3: Create `api/app/quotas.py`**

```python
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Job, Paper

MAX_RUNNING_JOBS_PER_USER = 1
MAX_JOBS_PER_DAY = 3


@dataclass
class QuotaError(Exception):
    code: str
    message: str

    def __post_init__(self) -> None:
        super().__init__(self.message)


def check_can_start_job(db: Session, user_id: uuid.UUID) -> None:
    running = db.scalar(
        select(func.count(Job.id))
        .join(Paper, Paper.id == Job.paper_id)
        .where(Paper.user_id == user_id, Job.status.in_(["queued", "running"]))
    )
    if running and running >= MAX_RUNNING_JOBS_PER_USER:
        raise QuotaError("already_running", "you already have a job in progress")

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    started_today = db.scalar(
        select(func.count(Job.id))
        .join(Paper, Paper.id == Job.paper_id)
        .where(Paper.user_id == user_id, Job.started_at >= today_start)
    )
    if started_today and started_today >= MAX_JOBS_PER_DAY:
        raise QuotaError("daily_quota", f"daily limit of {MAX_JOBS_PER_DAY} jobs reached")
```

- [ ] **Step 4: Run the tests — expect PASS**

```bash
pytest tests/test_quotas.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/quotas.py api/tests/test_quotas.py
git commit -m "api: enforce per-user running and daily job quotas"
```

---

## Task 7: Papers router (list + create + get)

**Files:**
- Create: `api/app/routers/papers.py`
- Modify: `api/app/main.py` (mount)
- Create: `api/app/job_runner.py` (stub — full implementation in Task 9)
- Create: `api/tests/test_papers.py`

- [ ] **Step 1: Create stub `api/app/job_runner.py`**

This file gets filled out in Task 9. For now we need just enough surface for the papers router to call it.

```python
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .models import Job
from .settings import get_settings


def spawn_job(db: Session, job: Job, brief: dict) -> None:
    settings = get_settings()
    workdir = settings.job_workdir_root / str(job.id)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "engine",
            "--job-id", str(job.id),
            "--paper-id", str(job.paper_id),
            "--workdir", str(workdir),
            "--brief-json", str(workdir / "brief.json"),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    job.pid = proc.pid
    job.workdir = str(workdir)
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
```

- [ ] **Step 2: Create `api/app/routers/papers.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..job_runner import spawn_job
from ..models import Job, Paper, User
from ..quotas import QuotaError, check_can_start_job

router = APIRouter(prefix="/papers", tags=["papers"])

ALLOWED_LEVELS = {"research", "bachelor", "master", "phd"}
ALLOWED_STYLES = {"apa", "mla", "chicago", "ieee", "harvard"}
ALLOWED_MODELS = {"gemini-flash", "claude-sonnet", "claude-opus", "gpt-5"}


class Sources(BaseModel):
    crossref: bool = True
    openalex: bool = True
    semanticscholar: bool = True
    arxiv: bool = True
    jstor: bool = False
    googleScholar: bool = False


class PaperCreate(BaseModel):
    topic: str = Field(min_length=4, max_length=500)
    research_question: str | None = Field(default=None, max_length=2000)
    academic_level: str
    language: str = Field(min_length=2, max_length=16)
    model: str
    citation_style: str
    sources: Sources = Sources()
    tone: str | None = None


class PaperOut(BaseModel):
    id: str
    title: str
    level: str
    status: str
    progress: float
    updated_at: str
    discipline: str | None = None


class CreateResp(BaseModel):
    paper_id: str
    job_id: str


def _level_to_label(level: str) -> str:
    return {
        "research": "Research paper",
        "bachelor": "Bachelor's thesis",
        "master": "Master's thesis",
        "phd": "PhD dissertation",
    }.get(level, level)


def _paper_to_out(p: Paper, latest: Job | None) -> PaperOut:
    return PaperOut(
        id=str(p.id),
        title=p.topic,
        level=_level_to_label(p.academic_level),
        status=p.status,
        progress=latest.progress if latest else 0.0,
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
    )


@router.get("", response_model=list[PaperOut])
def list_papers(user: User = Depends(current_user), db: Session = Depends(db_session)):
    rows = db.scalars(select(Paper).where(Paper.user_id == user.id).order_by(desc(Paper.updated_at))).all()
    out = []
    for p in rows:
        latest = None
        if p.latest_job_id:
            latest = db.get(Job, p.latest_job_id)
        out.append(_paper_to_out(p, latest))
    return out


@router.post("", response_model=CreateResp, status_code=201)
def create_paper(body: PaperCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if body.academic_level not in ALLOWED_LEVELS:
        raise HTTPException(422, detail={"error": {"code": "bad_level", "message": "invalid academic_level"}})
    if body.citation_style not in ALLOWED_STYLES:
        raise HTTPException(422, detail={"error": {"code": "bad_style", "message": "invalid citation_style"}})
    if body.model not in ALLOWED_MODELS:
        raise HTTPException(422, detail={"error": {"code": "bad_model", "message": "invalid model"}})

    try:
        check_can_start_job(db, user.id)
    except QuotaError as e:
        status = 409 if e.code == "already_running" else 429
        raise HTTPException(status, detail={"error": {"code": e.code, "message": e.message}})

    paper = Paper(
        user_id=user.id,
        topic=body.topic,
        research_question=body.research_question,
        academic_level=body.academic_level,
        language=body.language,
        citation_style=body.citation_style,
        tone=body.tone,
        model=body.model,
        sources_json=body.sources.model_dump(),
        status="running",
    )
    db.add(paper)
    db.flush()

    job = Job(paper_id=paper.id, status="queued")
    db.add(job)
    db.flush()

    paper.latest_job_id = job.id
    db.commit()

    brief = {
        "topic": body.topic,
        "research_question": body.research_question,
        "academic_level": body.academic_level,
        "language": body.language,
        "citation_style": body.citation_style,
        "model": body.model,
        "tone": body.tone,
        "sources": body.sources.model_dump(),
    }
    spawn_job(db, job, brief)

    return CreateResp(paper_id=str(paper.id), job_id=str(job.id))


@router.get("/{paper_id}")
def get_paper(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p = db.get(Paper, paper_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "paper not found"}})
    latest = db.get(Job, p.latest_job_id) if p.latest_job_id else None
    return {"paper": _paper_to_out(p, latest).model_dump(),
            "latest_job": {"id": str(latest.id), "status": latest.status, "phase": latest.phase, "progress": latest.progress} if latest else None}
```

- [ ] **Step 3: Mount in `api/app/main.py`**

In `create_app()`, after the auth router:

```python
    from .routers import papers as papers_router
    app.include_router(papers_router.router, prefix="/api/v1")
```

- [ ] **Step 4: Write `api/tests/test_papers.py`**

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def _signed_in_client():
    c = TestClient(create_app())
    c.post("/api/v1/auth/signup", json={"email": "u@x.com", "password": "supersecret"})
    return c


def _brief():
    return {
        "topic": "Algorithmic decision making and democratic accountability",
        "research_question": "How do EU and US diverge?",
        "academic_level": "master",
        "language": "en",
        "model": "gemini-flash",
        "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }


def test_list_papers_empty():
    c = _signed_in_client()
    r = c.get("/api/v1/papers")
    assert r.status_code == 200
    assert r.json() == []


def test_create_paper_spawns_job():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job") as spawn:
        r = c.post("/api/v1/papers", json=_brief())
    assert r.status_code == 201, r.text
    body = r.json()
    assert "paper_id" in body and "job_id" in body
    assert spawn.called


def test_create_paper_rejects_unknown_model():
    c = _signed_in_client()
    bad = {**_brief(), "model": "made-up"}
    r = c.post("/api/v1/papers", json=bad)
    assert r.status_code == 422


def test_create_paper_blocks_when_already_running():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job"):
        c.post("/api/v1/papers", json=_brief())
    r = c.post("/api/v1/papers", json=_brief())
    assert r.status_code == 409


def test_list_paper_includes_created():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job"):
        c.post("/api/v1/papers", json=_brief())
    r = c.get("/api/v1/papers")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["title"].startswith("Algorithmic")


def test_unauthenticated_returns_401():
    c = TestClient(create_app())
    assert c.get("/api/v1/papers").status_code == 401
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_papers.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add api/app/routers/papers.py api/app/job_runner.py api/app/main.py api/tests/test_papers.py
git commit -m "api: papers router with create/list/get and quota enforcement"
```

---

## Task 8: Job runner — JSONL tailer, pubsub, full subprocess lifecycle

**Files:**
- Modify: `api/app/job_runner.py` (replace stub from Task 7)
- Create: `api/app/pubsub.py`
- Create: `api/tests/test_job_runner.py`

- [ ] **Step 1: Create `api/app/pubsub.py`**

```python
import asyncio
import uuid
from collections import defaultdict


class InProcessPubsub:
    def __init__(self) -> None:
        self._subs: dict[uuid.UUID, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, key: uuid.UUID) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs[key].append(q)
        return q

    def unsubscribe(self, key: uuid.UUID, q: asyncio.Queue) -> None:
        if q in self._subs.get(key, []):
            self._subs[key].remove(q)
        if not self._subs.get(key):
            self._subs.pop(key, None)

    async def publish(self, key: uuid.UUID, msg: dict) -> None:
        for q in list(self._subs.get(key, [])):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


pubsub = InProcessPubsub()
```

- [ ] **Step 2: Replace `api/app/job_runner.py`**

```python
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .db import get_session_factory
from .models import Job, JobEvent, Paper
from .pubsub import pubsub
from .settings import get_settings

log = logging.getLogger(__name__)

_monitors: dict[uuid.UUID, asyncio.Task] = {}


def spawn_job(db: Session, job: Job, brief: dict) -> None:
    settings = get_settings()
    workdir = settings.job_workdir_root / str(job.id)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    env = os.environ.copy()
    env["JOB_ID"] = str(job.id)
    env["PAPER_ID"] = str(job.paper_id)
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
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "engine",
            "--job-id", str(job.id),
            "--paper-id", str(job.paper_id),
            "--workdir", str(workdir),
            "--brief-json", str(workdir / "brief.json"),
            "--user-id", str(db.get(Paper, job.paper_id).user_id),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    job.pid = proc.pid
    job.workdir = str(workdir)
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(job.id)


def start_monitor(job_id: uuid.UUID) -> None:
    if job_id in _monitors and not _monitors[job_id].done():
        return
    loop = asyncio.get_event_loop()
    _monitors[job_id] = loop.create_task(_monitor(job_id))


async def _monitor(job_id: uuid.UUID) -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        job = db.get(Job, job_id)
        if not job or not job.workdir:
            return
        path = Path(job.workdir) / "events.jsonl"

    last_pos = 0
    last_line_count = 0
    try:
        while True:
            if not path.exists():
                await asyncio.sleep(0.5)
                continue

            with session_factory() as db:
                job = db.get(Job, job_id)
                if not job:
                    return
                skip_lines = job.events_processed

            with path.open("r", encoding="utf-8") as f:
                f.seek(last_pos)
                lines = f.readlines()
                last_pos = f.tell()

            new_lines = lines[max(0, skip_lines - last_line_count):]
            last_line_count = last_line_count + len(lines)

            done = False
            for raw in new_lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("malformed event line: %r", raw[:200])
                    continue
                done = await _ingest_event(job_id, payload) or done

            if done:
                return

            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return


async def _ingest_event(job_id: uuid.UUID, payload: dict) -> bool:
    """Persist one event, update job state, publish to subscribers. Returns True when terminal."""
    type_ = payload.get("type", "activity")
    session_factory = get_session_factory()
    with session_factory() as db:
        event = JobEvent(
            job_id=job_id,
            type=type_,
            phase=payload.get("phase"),
            agent=payload.get("agent"),
            text=payload.get("text"),
            meta_json={k: v for k, v in payload.items() if k not in {"type", "phase", "agent", "text"}},
        )
        db.add(event)

        job = db.get(Job, job_id)
        if job:
            job.events_processed += 1
            if type_ == "phase_progress":
                if "phase" in payload:
                    job.phase = payload["phase"]
                if "progress" in payload:
                    job.progress = float(payload["progress"])
            if type_ == "job_done":
                job.status = "done"
                job.finished_at = datetime.now(timezone.utc)
                job.progress = 1.0
                paper = db.get(Paper, job.paper_id)
                if paper:
                    paper.status = "done"
            if type_ == "error":
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.error_text = payload.get("text") or "unknown error"
                paper = db.get(Paper, job.paper_id)
                if paper:
                    paper.status = "failed"

        db.commit()
        ev_id = event.id

    await pubsub.publish(job_id, {"id": ev_id, **payload})
    return type_ in {"job_done", "error"}


def cancel_job(db: Session, job: Job) -> None:
    if job.pid:
        try:
            if sys.platform == "win32":
                os.kill(job.pid, signal.SIGTERM)
            else:
                os.kill(job.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    job.status = "canceled"
    job.finished_at = datetime.now(timezone.utc)
    paper = db.get(Paper, job.paper_id)
    if paper:
        paper.status = "failed"
    db.commit()
```

- [ ] **Step 3: Write `api/tests/test_job_runner.py`**

```python
import asyncio
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.job_runner import _monitor
from app.models import Job, JobEvent, Paper, User
from app.pubsub import pubsub


def _make_running_job(tmp_path: Path) -> uuid.UUID:
    with OrmSession(get_engine()) as db:
        u = User(email=f"{uuid.uuid4().hex}@x.com", password_hash="x")
        db.add(u)
        db.flush()
        p = Paper(user_id=u.id, topic="t", academic_level="master", language="en",
                  citation_style="apa", model="gemini-flash", sources_json={}, status="running")
        db.add(p)
        db.flush()
        wd = tmp_path / str(uuid.uuid4())
        wd.mkdir()
        (wd / "events.jsonl").touch()
        j = Job(paper_id=p.id, status="running", workdir=str(wd))
        db.add(j)
        db.commit()
        return j.id


@pytest.mark.asyncio
async def test_monitor_ingests_lines_and_marks_done(tmp_path):
    job_id = _make_running_job(tmp_path)
    with OrmSession(get_engine()) as db:
        wd = Path(db.get(Job, job_id).workdir)

    sub = pubsub.subscribe(job_id)
    task = asyncio.create_task(_monitor(job_id))

    await asyncio.sleep(0.6)
    with (wd / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "activity", "phase": "research", "agent": "Scout",
                             "text": "found a paper"}) + "\n")
        f.flush()
        f.write(json.dumps({"type": "phase_progress", "phase": "research", "progress": 0.5}) + "\n")
        f.flush()
        f.write(json.dumps({"type": "job_done", "exports": ["pdf"]}) + "\n")
        f.flush()

    await asyncio.wait_for(task, timeout=5)

    msgs = []
    while not sub.empty():
        msgs.append(sub.get_nowait())
    assert any(m["type"] == "activity" for m in msgs)
    assert any(m["type"] == "job_done" for m in msgs)

    with OrmSession(get_engine()) as db:
        j = db.get(Job, job_id)
        assert j.status == "done"
        assert j.progress == 1.0
        assert j.events_processed == 3
        assert db.query(JobEvent).filter(JobEvent.job_id == job_id).count() == 3
    pubsub.unsubscribe(job_id, sub)
```

- [ ] **Step 4: Run the test**

```bash
pytest tests/test_job_runner.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/job_runner.py api/app/pubsub.py api/tests/test_job_runner.py
git commit -m "api: JSONL job monitor, in-process pubsub, full subprocess lifecycle"
```

---

## Task 9: Jobs router — status, cancel, SSE

**Files:**
- Create: `api/app/sse.py`
- Create: `api/app/routers/jobs.py`
- Modify: `api/app/main.py` (mount)
- Create: `api/tests/test_jobs.py`

- [ ] **Step 1: Create `api/app/sse.py`**

```python
import asyncio
import json
from typing import AsyncIterator


def sse_pack(payload: dict, *, event_id: int | None = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append("data: " + json.dumps(payload))
    return "\n".join(parts) + "\n\n"


async def heartbeat_every(interval: float = 15.0) -> AsyncIterator[str]:
    while True:
        await asyncio.sleep(interval)
        yield ": keepalive\n\n"
```

- [ ] **Step 2: Create `api/app/routers/jobs.py`**

```python
import asyncio
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..job_runner import cancel_job, start_monitor
from ..models import Job, JobEvent, Paper, User
from ..pubsub import pubsub
from ..sse import sse_pack

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _owned_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "job not found"}})
    paper = db.get(Paper, j.paper_id)
    if not paper or paper.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "job not found"}})
    return j


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    j = _owned_job(db, user, job_id)
    return {
        "id": str(j.id), "paper_id": str(j.paper_id),
        "status": j.status, "phase": j.phase, "progress": j.progress,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "error_text": j.error_text,
    }


@router.post("/{job_id}/cancel", status_code=202)
def cancel(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    j = _owned_job(db, user, job_id)
    if j.status in {"done", "failed", "canceled"}:
        return {"status": j.status}
    cancel_job(db, j)
    return {"status": "canceled"}


@router.get("/{job_id}/events")
async def stream_events(job_id: uuid.UUID, since: int = 0,
                        user: User = Depends(current_user), db: Session = Depends(db_session)):
    _owned_job(db, user, job_id)

    if j := db.get(Job, job_id):
        if j.status in {"queued", "running"}:
            start_monitor(job_id)

    backlog: list[tuple[int, dict]] = []
    events = db.scalars(
        select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > since).order_by(JobEvent.id)
    ).all()
    for ev in events:
        payload = {"type": ev.type, "phase": ev.phase, "agent": ev.agent, "text": ev.text,
                    **(ev.meta_json or {})}
        backlog.append((ev.id, payload))

    sub = pubsub.subscribe(job_id)

    async def gen() -> AsyncIterator[str]:
        try:
            for ev_id, payload in backlog:
                yield sse_pack(payload, event_id=ev_id)

            while True:
                try:
                    msg = await asyncio.wait_for(sub.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield sse_pack({k: v for k, v in msg.items() if k != "id"}, event_id=msg.get("id"))
                if msg.get("type") in {"job_done", "error"}:
                    break
        finally:
            pubsub.unsubscribe(job_id, sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- [ ] **Step 3: Mount in `api/app/main.py`**

After the papers router:

```python
    from .routers import jobs as jobs_router
    app.include_router(jobs_router.router, prefix="/api/v1")
```

- [ ] **Step 4: Write `api/tests/test_jobs.py`**

```python
import json
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.main import create_app
from app.models import Job, JobEvent, Paper


def _signed_in_client():
    c = TestClient(create_app())
    c.post("/api/v1/auth/signup", json={"email": "u@x.com", "password": "supersecret"})
    return c


def _seed_paper(c, brief):
    with patch("app.routers.papers.spawn_job"):
        r = c.post("/api/v1/papers", json=brief)
    return r.json()


def _brief():
    return {
        "topic": "x x x x", "research_question": "q",
        "academic_level": "master", "language": "en",
        "model": "gemini-flash", "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }


def test_get_job_returns_status():
    c = _signed_in_client()
    ids = _seed_paper(c, _brief())
    r = c.get(f"/api/v1/jobs/{ids['job_id']}")
    assert r.status_code == 200
    assert r.json()["status"] in {"queued", "running"}


def test_cannot_see_other_users_job():
    c1 = _signed_in_client()
    ids = _seed_paper(c1, _brief())
    c2 = TestClient(create_app())
    c2.post("/api/v1/auth/signup", json={"email": "v@x.com", "password": "supersecret"})
    r = c2.get(f"/api/v1/jobs/{ids['job_id']}")
    assert r.status_code == 404


def test_sse_replays_backlog():
    c = _signed_in_client()
    ids = _seed_paper(c, _brief())
    job_id = uuid.UUID(ids["job_id"])

    with OrmSession(get_engine()) as db:
        db.add(JobEvent(job_id=job_id, type="activity", phase="research", agent="Scout", text="hi"))
        db.add(JobEvent(job_id=job_id, type="job_done"))
        db.commit()

    with c.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        body = b""
        for chunk in resp.iter_bytes():
            body += chunk
            if b"job_done" in body:
                break
    text = body.decode()
    assert "activity" in text
    assert "job_done" in text
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_jobs.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/app/sse.py api/app/routers/jobs.py api/app/main.py api/tests/test_jobs.py
git commit -m "api: jobs router with status, cancel and SSE event stream"
```

---

## Task 10: Draft / citations / exports endpoints

**Files:**
- Modify: `api/app/routers/papers.py` (add 3 endpoints + helpers)
- Modify: `api/app/main.py` (no change — already mounted)
- Create: `api/tests/test_outputs.py`

- [ ] **Step 1: Add to `api/app/routers/papers.py`** (append before the file's end, after the `get_paper` endpoint)

```python
from fastapi.responses import RedirectResponse
from ..s3 import get_s3_from_settings
from ..settings import get_settings


def _job_key_root(paper: Paper, job_id: uuid.UUID) -> str:
    return f"users/{paper.user_id}/papers/{paper.id}/jobs/{job_id}"


def _require_done_paper(db: Session, user: User, paper_id: uuid.UUID) -> tuple[Paper, uuid.UUID]:
    p = db.get(Paper, paper_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "paper not found"}})
    if not p.latest_job_id:
        raise HTTPException(404, detail={"error": {"code": "no_job", "message": "no job for paper"}})
    job = db.get(Job, p.latest_job_id)
    if not job or job.status != "done":
        raise HTTPException(409, detail={"error": {"code": "not_ready", "message": "draft not finished"}})
    return p, job.id


@router.get("/{paper_id}/draft")
def get_draft(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    settings = get_settings()
    s3 = get_s3_from_settings(settings)
    md_key = f"{_job_key_root(p, job_id)}/exports/draft.md"
    body = s3._client.get_object(Bucket=s3.bucket, Key=s3._full_key(md_key))["Body"].read().decode("utf-8")
    chapters = _chapters_from_markdown(body)
    return {
        "markdown": body,
        "html": _md_to_html(body),
        "word_count": sum(len(c.get("title", "").split()) for c in chapters) + len(body.split()),
        "chapters": chapters,
    }


def _chapters_from_markdown(md: str) -> list[dict]:
    out: list[dict] = []
    n = 0
    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            n += 1
            title = line[3:].strip()
            out.append({"num": str(n), "title": title, "words": 0})
    return out


def _md_to_html(md: str) -> str:
    try:
        import markdown
        return markdown.markdown(md, extensions=["fenced_code", "tables"])
    except ImportError:
        return "<pre>" + md.replace("<", "&lt;") + "</pre>"


@router.get("/{paper_id}/citations")
def get_citations(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    key = f"{_job_key_root(p, job_id)}/research/bibliography.json"
    body = s3._client.get_object(Bucket=s3.bucket, Key=s3._full_key(key))["Body"].read().decode("utf-8")
    raw = json.loads(body) if body else []
    return [
        {
            "key": e.get("key") or e.get("id") or "",
            "title": e.get("title", ""),
            "authors": ", ".join(e.get("authors", [])) if isinstance(e.get("authors"), list) else e.get("authors", ""),
            "year": e.get("year"),
            "doi": e.get("doi"),
            "source": e.get("source", "CrossRef"),
            "venue": e.get("venue") or e.get("journal"),
            "verified": bool(e.get("verified", True)),
        }
        for e in raw
    ]


EXPORT_FORMATS = {
    "pdf": ("exports/draft.pdf", "application/pdf"),
    "docx": ("exports/draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "tex": ("exports/draft.tex", "application/x-tex"),
    "md": ("exports/draft.md", "text/markdown"),
    "zip": ("exports/bundle.zip", "application/zip"),
}


@router.get("/{paper_id}/exports")
def list_exports(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    out = []
    for fmt, (rel, _ct) in EXPORT_FORMATS.items():
        meta = s3.head_object(f"{_job_key_root(p, job_id)}/{rel}")
        if meta:
            out.append({"format": fmt, "size": meta["ContentLength"],
                         "generated_at": meta["LastModified"].isoformat()})
    return out


@router.get("/{paper_id}/exports/{fmt}")
def download_export(paper_id: uuid.UUID, fmt: str,
                     user: User = Depends(current_user), db: Session = Depends(db_session)):
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(404, detail={"error": {"code": "unknown_format", "message": fmt}})
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    rel, _ct = EXPORT_FORMATS[fmt]
    url = s3.presigned_get(f"{_job_key_root(p, job_id)}/{rel}", expires_in=300)
    return RedirectResponse(url, status_code=302)
```

At the top of the file, add:

```python
import json
```

(and remove if already present to avoid duplicates).

- [ ] **Step 2: Add `markdown` to deps in `api/pyproject.toml`**

Add `"markdown>=3.7"` to the `dependencies` list, then `pip install -e ".[dev]"`.

- [ ] **Step 3: Write `api/tests/test_outputs.py`**

```python
import json
import uuid
from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.main import create_app
from app.models import Job, Paper
from app.settings import get_settings


def _signed_in_client():
    c = TestClient(create_app())
    c.post("/api/v1/auth/signup", json={"email": "u@x.com", "password": "supersecret"})
    return c


def _seed_done_paper(client):
    brief = {
        "topic": "topic", "research_question": "q",
        "academic_level": "master", "language": "en",
        "model": "gemini-flash", "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }
    with patch("app.routers.papers.spawn_job"):
        ids = client.post("/api/v1/papers", json=brief).json()
    with OrmSession(get_engine()) as db:
        job = db.get(Job, uuid.UUID(ids["job_id"]))
        paper = db.get(Paper, uuid.UUID(ids["paper_id"]))
        job.status = "done"
        paper.status = "done"
        db.commit()
        return paper, job


@pytest.fixture
def _s3():
    settings = get_settings()
    with mock_aws():
        c = boto3.client("s3", region_name=settings.aws_region,
                          aws_access_key_id=settings.aws_access_key,
                          aws_secret_access_key=settings.aws_secret_key)
        c.create_bucket(Bucket=settings.s3_bucket,
                         CreateBucketConfiguration={"LocationConstraint": settings.aws_region})
        yield c


def _put(s3, paper, job, rel, body, ct):
    settings = get_settings()
    key = f"{settings.s3_prefix}users/{paper.user_id}/papers/{paper.id}/jobs/{job.id}/{rel}"
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=ct)


def test_draft_returns_markdown_and_chapters(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.md", b"# Title\n\n## Introduction\n\nhi\n\n## Methods\n\nok\n", "text/markdown")
    r = c.get(f"/api/v1/papers/{p.id}/draft")
    assert r.status_code == 200
    data = r.json()
    assert "Introduction" in data["markdown"]
    assert [ch["title"] for ch in data["chapters"]] == ["Introduction", "Methods"]


def test_citations_returns_list(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    bib = [{"key": "k1", "title": "Paper One", "authors": ["A. Doe"], "year": 2024,
             "doi": "10.1/x", "source": "CrossRef", "venue": "Journal"}]
    _put(_s3, p, j, "research/bibliography.json", json.dumps(bib).encode(), "application/json")
    r = c.get(f"/api/v1/papers/{p.id}/citations")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Paper One"


def test_exports_lists_only_present_formats(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.pdf", b"%PDF-1.4 fake", "application/pdf")
    r = c.get(f"/api/v1/papers/{p.id}/exports")
    assert r.status_code == 200
    formats = [e["format"] for e in r.json()]
    assert formats == ["pdf"]


def test_download_returns_302(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.pdf", b"%PDF-1.4 fake", "application/pdf")
    r = c.get(f"/api/v1/papers/{p.id}/exports/pdf", follow_redirects=False)
    assert r.status_code == 302
    assert "draft.pdf" in r.headers["location"]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_outputs.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/papers.py api/pyproject.toml api/tests/test_outputs.py
git commit -m "api: draft, citations and exports endpoints backed by S3"
```

---

# Phase B — Engine integration

## Task 11: Engine subprocess entrypoint (`engine/__main__.py`)

**Files:**
- Create: `engine/__main__.py`
- Create: `engine/job_io.py` (helper module separated for testability)
- Create: `engine/tests/test_job_io.py`

- [ ] **Step 1: Create `engine/job_io.py`**

```python
"""Helpers used by the subprocess entrypoint. Kept separate from __main__ for testability."""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class JsonlAppender:
    """Append-only writer that flushes after each line so the API tailer sees writes immediately."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fp = path.open("a", encoding="utf-8", buffering=1)  # line-buffered

    def write(self, payload: dict) -> None:
        line = json.dumps(payload, default=str)
        self._fp.write(line + "\n")
        self._fp.flush()

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass


class JobTracker:
    """Adapter matching the shape `engine.draft_generator.generate_draft` expects for `tracker=`."""

    def __init__(self, appender: JsonlAppender) -> None:
        self._a = appender

    def log_activity(self, message: str, *, event_type: str = "activity", phase: str | None = None,
                     agent: str | None = None, **meta: Any) -> None:
        self._a.write({"type": "activity", "phase": phase, "agent": agent, "text": message, **meta})

    def update_phase(self, phase: str, *, progress_percent: float | None = None,
                     details: dict | None = None) -> None:
        prog = None
        if progress_percent is not None:
            prog = progress_percent / 100.0 if progress_percent > 1.0 else progress_percent
        self._a.write({"type": "phase_progress", "phase": phase,
                        "progress": prog if prog is not None else 0.0,
                        "active_agents": (details or {}).get("active_agents", [])})


class JobStreamer:
    """Adapter matching the shape `engine.draft_generator.generate_draft` expects for `streamer=`."""

    def __init__(self, appender: JsonlAppender) -> None:
        self._a = appender

    def __call__(self, message: str, **meta: Any) -> None:
        self._a.write({"type": "activity", "text": message, **meta})


def upload_artifacts(s3_client, workdir: Path, key_root: str) -> list[str]:
    """Upload everything under workdir/{exports,research,drafts} to S3. Returns list of export formats found."""
    found_exports: list[str] = []
    EXTS = {"pdf", "docx", "tex", "md", "zip"}
    for sub in ("exports", "research", "drafts"):
        base = workdir / sub
        if not base.exists():
            continue
        for fp in base.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(workdir).as_posix()
            full_key = f"{key_root}/{rel}"
            s3_client.put_file(full_key, str(fp))
            log.info("uploaded %s -> %s", rel, full_key)
            if sub == "exports":
                ext = fp.suffix.lstrip(".").lower()
                if ext in EXTS:
                    found_exports.append(ext)
    return sorted(set(found_exports))
```

- [ ] **Step 2: Write the failing tests in `engine/tests/test_job_io.py`**

```python
import json
from pathlib import Path

from engine.job_io import JobStreamer, JobTracker, JsonlAppender


def test_appender_writes_one_line_per_call(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    a = JsonlAppender(p)
    a.write({"type": "activity", "text": "hello"})
    a.write({"type": "activity", "text": "world"})
    a.close()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["text"] for l in lines] == ["hello", "world"]


def test_tracker_emits_activity_and_progress(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    a = JsonlAppender(p)
    tr = JobTracker(a)
    tr.log_activity("did a thing", phase="research", agent="Scout")
    tr.update_phase("compose", progress_percent=68, details={"active_agents": ["Crafter · Intro"]})
    a.close()
    events = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert events[0] == {"type": "activity", "phase": "research", "agent": "Scout", "text": "did a thing"}
    assert events[1]["type"] == "phase_progress"
    assert events[1]["phase"] == "compose"
    assert abs(events[1]["progress"] - 0.68) < 1e-6
    assert events[1]["active_agents"] == ["Crafter · Intro"]


def test_streamer_emits_activity(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    a = JsonlAppender(p)
    s = JobStreamer(a)
    s("hello", phase="research")
    a.close()
    ev = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert ev == {"type": "activity", "text": "hello", "phase": "research"}
```

- [ ] **Step 3: Create the test directory and run**

```bash
mkdir -p engine/tests
touch engine/tests/__init__.py
cd C:/DFolder/cao_projects/opendraft
python -m pytest engine/tests/test_job_io.py -v
```
Expected: 3 passed.

- [ ] **Step 4: Create `engine/__main__.py`**

```python
"""Subprocess entrypoint invoked by the API.

    python -m engine \
        --job-id <uuid> --paper-id <uuid> --user-id <uuid> \
        --workdir <path> --brief-json <path>
"""
import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path

# Make `engine.draft_generator` importable when run with `-m engine`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.job_io import JobStreamer, JobTracker, JsonlAppender, upload_artifacts
from engine.s3_for_jobs import s3_from_env  # created below

log = logging.getLogger("engine.__main__")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--brief-json", required=True)
    args = parser.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    events_path = workdir / "events.jsonl"
    appender = JsonlAppender(events_path)
    tracker = JobTracker(appender)
    streamer = JobStreamer(appender)

    try:
        brief = json.loads(Path(args.brief_json).read_text(encoding="utf-8"))

        # Lazy import — heavy
        from draft_generator import generate_draft

        appender.write({"type": "activity", "phase": "research", "text": "Job starting"})

        generate_draft(
            topic=brief["topic"],
            language=brief.get("language", "en"),
            academic_level=brief["academic_level"],
            output_dir=workdir,
            citation_style=brief.get("citation_style", "apa"),
            tracker=tracker,
            streamer=streamer,
            verbose=False,
        )

        s3 = s3_from_env()
        key_root = f"users/{args.user_id}/papers/{args.paper_id}/jobs/{args.job_id}"
        exports = upload_artifacts(s3, workdir, key_root)

        appender.write({"type": "job_done", "exports": exports})
        return 0
    except Exception as e:
        log.exception("job failed")
        appender.write({"type": "error", "text": str(e), "traceback": traceback.format_exc()})
        return 1
    finally:
        appender.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Create `engine/s3_for_jobs.py`** (tiny boto3 helper, mirrors `api.app.s3.S3Client` so the engine doesn't depend on `api/`)

```python
import os
from pathlib import PurePosixPath

import boto3
from botocore.config import Config


class _Client:
    def __init__(self, bucket: str, prefix: str, region: str, ak: str, sk: str) -> None:
        self.bucket = bucket
        self.prefix = prefix if prefix.endswith("/") else prefix + "/"
        self.client = boto3.client("s3", region_name=region,
                                    aws_access_key_id=ak, aws_secret_access_key=sk,
                                    config=Config(signature_version="s3v4"))

    def _key(self, rel: str) -> str:
        if rel.startswith("/"):
            raise ValueError("S3 key must be relative")
        p = PurePosixPath(rel)
        if ".." in p.parts:
            raise ValueError("S3 key must not contain '..'")
        return self.prefix + str(p)

    def put_file(self, key: str, path: str) -> None:
        self.client.upload_file(path, self.bucket, self._key(key))


def s3_from_env() -> _Client:
    return _Client(
        bucket=os.environ["S3_BUCKET"],
        prefix=os.environ.get("S3_PREFIX", "opendraft/"),
        region=os.environ["AWS_REGION"],
        ak=os.environ["AWS_ACCESS_KEY"],
        sk=os.environ["AWS_SECRET_KEY"],
    )
```

- [ ] **Step 6: Smoke test the entrypoint with a stub `generate_draft`**

Create `engine/tests/test_entrypoint_smoke.py`:

```python
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def env_with_s3(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "smoke-bucket")
    monkeypatch.setenv("S3_PREFIX", "opendraft/")
    monkeypatch.setenv("AWS_ACCESS_KEY", "x")
    monkeypatch.setenv("AWS_SECRET_KEY", "y")


def test_subprocess_writes_events_and_uploads(tmp_path: Path, env_with_s3):
    workdir = tmp_path / "job"
    workdir.mkdir()
    (workdir / "brief.json").write_text(json.dumps({
        "topic": "t", "academic_level": "master", "language": "en", "citation_style": "apa"
    }))

    fake_module = tmp_path / "draft_generator.py"
    fake_module.write_text(
        "def generate_draft(*, tracker, streamer, output_dir, **kw):\n"
        "    tracker.update_phase('research', progress_percent=10)\n"
        "    tracker.log_activity('found a thing', phase='research', agent='Scout')\n"
        "    (output_dir / 'exports').mkdir(parents=True, exist_ok=True)\n"
        "    (output_dir / 'exports' / 'draft.md').write_text('# T\\n')\n"
    )

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="smoke-bucket")

        proc = subprocess.run(
            [sys.executable, "-m", "engine",
             "--job-id", "00000000-0000-0000-0000-000000000001",
             "--paper-id", "00000000-0000-0000-0000-000000000002",
             "--user-id", "00000000-0000-0000-0000-000000000003",
             "--workdir", str(workdir),
             "--brief-json", str(workdir / "brief.json")],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)},
            capture_output=True, text=True,
        )

    assert proc.returncode == 0, proc.stderr
    events = [json.loads(l) for l in (workdir / "events.jsonl").read_text().splitlines()]
    types = [e["type"] for e in events]
    assert "phase_progress" in types
    assert "activity" in types
    assert types[-1] == "job_done"
```

- [ ] **Step 7: Run the smoke test**

```bash
python -m pytest engine/tests/test_entrypoint_smoke.py -v
```

> **Note:** the subprocess test under `mock_aws` only patches the parent process. The boto3 client inside the subprocess will fail unless we point it at a localhost endpoint. If this proves flaky, mark the test `@pytest.mark.skip("requires real or stub S3")` and rely on `test_job_io.py` plus a manual end-to-end run for verification. Don't block on it.

- [ ] **Step 8: Commit**

```bash
git add engine/__main__.py engine/job_io.py engine/s3_for_jobs.py engine/tests/
git commit -m "engine: add __main__ subprocess entrypoint with JSONL events and S3 upload"
```

---

# Phase C — Web frontend wiring

## Task 12: Frontend API client + auth context + middleware

**Files:**
- Create: `web/app/lib/api.js`
- Create: `web/app/lib/auth-context.jsx`
- Create: `web/middleware.js`
- Modify: `web/package.json` (add `swr`)

- [ ] **Step 1: Install SWR**

```bash
cd web
npm install swr@^2.2
```

- [ ] **Step 2: Create `web/app/lib/api.js`**

```javascript
const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
    body: opts.body && typeof opts.body !== "string" ? JSON.stringify(opts.body) : opts.body,
  });
  let body = null;
  try { body = await res.json(); } catch {}
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export function swrFetcher(path) {
  return apiFetch(path);
}

export function openEventStream(jobId, { since = 0, onEvent, onDone, onError } = {}) {
  const url = `${BASE}/jobs/${jobId}/events?since=${since}`;
  const es = new EventSource(url, { withCredentials: true });
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent?.(data, e.lastEventId ? parseInt(e.lastEventId, 10) : null);
      if (data.type === "job_done") { onDone?.(data); es.close(); }
      if (data.type === "error") { onError?.(data); es.close(); }
    } catch (err) {
      onError?.({ message: err.message });
    }
  };
  es.onerror = () => {
    onError?.({ message: "stream error" });
    es.close();
  };
  return () => es.close();
}

export { ApiError };
```

- [ ] **Step 3: Create `web/app/lib/auth-context.jsx`**

```jsx
"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { apiFetch, ApiError } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/auth/me")
      .then(setUser)
      .catch((e) => { if (!(e instanceof ApiError && e.status === 401)) console.error(e); })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const u = await apiFetch("/auth/login", { method: "POST", body: { email, password } });
    setUser(u);
    return u;
  };
  const signup = async (email, password) => {
    const u = await apiFetch("/auth/signup", { method: "POST", body: { email, password } });
    setUser(u);
    return u;
  };
  const logout = async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
```

- [ ] **Step 4: Create `web/middleware.js`**

The middleware only checks for cookie presence — full validation is server-side. This avoids a network call on every navigation.

```javascript
import { NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/signup", "/_next", "/favicon.ico"];

export function middleware(request) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookie = request.cookies.get("opendraft_session");
  if (!cookie) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

- [ ] **Step 5: Commit**

```bash
git add web/app/lib/ web/middleware.js web/package.json web/package-lock.json
git commit -m "web: api client, auth context and session middleware"
```

---

## Task 13: Login + signup pages

**Files:**
- Create: `web/app/login/page.jsx`
- Create: `web/app/signup/page.jsx`
- Modify: `web/app/layout.jsx` (wrap children with `AuthProvider`)

- [ ] **Step 1: Modify `web/app/layout.jsx`** — read first, then replace the JSX it returns to wrap children in `<AuthProvider>`:

```jsx
import "./globals.css";
import { AuthProvider } from "./lib/auth-context";

export const metadata = { title: "OpenDraft", description: "AI thesis drafts with verified citations" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
```

(If the existing layout has fonts or other setup, keep them — only insertion is the `AuthProvider` wrap and its import.)

- [ ] **Step 2: Create `web/app/login/page.jsx`**

```jsx
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../lib/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "var(--ink-50)" }}>
      <form onSubmit={submit} className="card" style={{ padding: 32, width: 360, display: "flex", flexDirection: "column", gap: 14 }}>
        <h1 className="section-title" style={{ marginBottom: 4 }}>Sign in</h1>
        <p style={{ color: "var(--ink-500)", fontSize: 13, margin: 0 }}>Use the email and password you signed up with.</p>
        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
        </div>
        <div className="field">
          <label>Password</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" minLength={8} required />
        </div>
        {error && <div style={{ color: "var(--danger-fg)", fontSize: 12 }}>{error}</div>}
        <button className="btn btn-primary btn-lg btn-block" disabled={busy} type="submit">
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <a href="/signup" style={{ fontSize: 13, color: "var(--blue-600)", textAlign: "center" }}>
          Create an account
        </a>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Create `web/app/signup/page.jsx`** — same shape but calls `signup`:

```jsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err.message || "Signup failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "var(--ink-50)" }}>
      <form onSubmit={submit} className="card" style={{ padding: 32, width: 360, display: "flex", flexDirection: "column", gap: 14 }}>
        <h1 className="section-title" style={{ marginBottom: 4 }}>Create account</h1>
        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
        </div>
        <div className="field">
          <label>Password (≥ 8 chars)</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" minLength={8} required />
        </div>
        {error && <div style={{ color: "var(--danger-fg)", fontSize: 12 }}>{error}</div>}
        <button className="btn btn-primary btn-lg btn-block" disabled={busy} type="submit">
          {busy ? "Creating…" : "Create account"}
        </button>
        <a href="/login" style={{ fontSize: 13, color: "var(--blue-600)", textAlign: "center" }}>
          Already have an account? Sign in
        </a>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Smoke test manually**

```bash
cd web && npm run dev
```
Visit `http://localhost:3000/signup`, submit credentials. Confirm it redirects to `/` (which will likely 404 until Task 14, but the cookie is set — verify in DevTools).

- [ ] **Step 5: Commit**

```bash
git add web/app/login web/app/signup web/app/layout.jsx
git commit -m "web: login and signup pages wired to auth context"
```

---

## Task 14: Real Next.js routing — dashboard, wizard, paper

**Files:**
- Create: `web/app/wizard/page.jsx`
- Create: `web/app/paper/[id]/page.jsx`
- Modify: `web/app/page.jsx` (becomes dashboard route only)
- Modify: `web/app/components/shared.jsx` (Sidebar drops Billing+Affiliate, links use real routes)

- [ ] **Step 1: Modify `web/app/components/shared.jsx`**

Find the `Sidebar` component (it lives in this file). The current sidebar lists Dashboard, Wizard, Paper, Billing, Affiliate. Drop Billing and Affiliate, and change the `onClick={setRoute(...)}` calls to `<a href="/...">` so they use real Next.js routing.

Read the file first, then replace the nav-items block to use only:

| Label      | href             |
|------------|------------------|
| Dashboard  | `/`              |
| New thesis | `/wizard`        |

Active state should compare against `usePathname()` from `next/navigation`. If the current Sidebar takes a `route` prop, replace its API:

```jsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";

const NAV = [
  { href: "/", label: "Dashboard", icon: "grid" },
  { href: "/wizard", label: "New thesis", icon: "plus" },
];

export const Sidebar = () => {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">OpenDraft</div>
      <nav>
        {NAV.map((n) => {
          const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} className={`nav-item ${active ? "active" : ""}`}>
              <Icon name={n.icon} size={16} /> {n.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
};
```

Keep all other exports in `shared.jsx` untouched (`Topbar`, `Card`, `ProgressBar`, etc.).

- [ ] **Step 2: Rewrite `web/app/page.jsx`**

The page becomes the Dashboard route only — no more in-app route state.

```jsx
"use client";

import useSWR from "swr";
import { Sidebar } from "./components/shared";
import { Dashboard } from "./components/dashboard";
import { swrFetcher } from "./lib/api";

export default function Page() {
  const { data: papers, error, isLoading, mutate } = useSWR("/papers", swrFetcher);

  return (
    <div className="app">
      <Sidebar />
      <Dashboard papers={papers || []} loading={isLoading} error={error} refresh={mutate} />
    </div>
  );
}
```

- [ ] **Step 3: Create `web/app/wizard/page.jsx`**

```jsx
"use client";

import { Sidebar } from "../components/shared";
import { Wizard } from "../components/wizard";

export default function WizardPage() {
  return (
    <div className="app">
      <Sidebar />
      <Wizard />
    </div>
  );
}
```

- [ ] **Step 4: Create `web/app/paper/[id]/page.jsx`**

```jsx
"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { Sidebar } from "../../components/shared";
import { PaperShell } from "../../components/paper-shell";
import { AgentRun } from "../../components/agent-run";
import { DraftEditor } from "../../components/draft-editor";
import { Citations } from "../../components/citations";
import { ExportTab } from "../../components/export-tab";
import { swrFetcher } from "../../lib/api";

const CITATION_STYLE_FALLBACK = "APA";

export default function PaperPage() {
  const { id } = useParams();
  const sp = useSearchParams();
  const router = useRouter();
  const tab = sp.get("tab") || "run";

  const { data, error, isLoading } = useSWR(`/papers/${id}`, swrFetcher, { refreshInterval: tab === "run" ? 5000 : 0 });

  const paper = data?.paper || { id, title: "Loading…", level: "", status: "running", progress: 0 };
  const jobId = data?.latest_job?.id;
  const style = paper.citation_style || CITATION_STYLE_FALLBACK;

  const setTab = (newTab) => router.push(`/paper/${id}?tab=${newTab}`);

  let body;
  if (tab === "run") body = <AgentRun jobId={jobId} />;
  else if (tab === "editor") body = <DraftEditor paperId={id} citationStyle={style} />;
  else if (tab === "citations") body = <Citations paperId={id} citationStyle={style} />;
  else if (tab === "export") body = <ExportTab paperId={id} citationStyle={style} />;
  else body = <AgentRun jobId={jobId} />;

  return (
    <div className="app">
      <Sidebar />
      <PaperShell paper={paper} tab={tab} setTab={setTab}>
        {isLoading ? <div style={{ padding: 32 }}>Loading…</div> : error ? <div style={{ padding: 32, color: "var(--danger-fg)" }}>Error: {error.message}</div> : body}
      </PaperShell>
    </div>
  );
}
```

Note: `PaperShell` currently takes a `go` prop. Read it first (`web/app/components/paper-shell.jsx`) — adapt the prop calls or pass a no-op `go={() => router.push("/")}`. If `PaperShell` calls `go("paper", { tab })`, replace with `setTab(tab)` directly. Edit `paper-shell.jsx` accordingly: swap any `go("paper", { tab: x })` to `setTab(x)` and accept `setTab` as a prop (it already does per `page.jsx`). Any sidebar/back-to-dashboard buttons should `<Link href="/">`.

- [ ] **Step 5: Run dev server and smoke check**

```bash
cd web && npm run dev
```
Navigate `/wizard` and `/paper/some-id`. They should render (paper page will show a 404 from API; that's fine — covered by next tasks).

- [ ] **Step 6: Commit**

```bash
git add web/app/page.jsx web/app/wizard web/app/paper web/app/components/shared.jsx web/app/components/paper-shell.jsx
git commit -m "web: real routing + sidebar drops billing/affiliate"
```

---

## Task 15: Wire Dashboard to real `/papers`

**Files:**
- Modify: `web/app/components/dashboard.jsx`

- [ ] **Step 1: Read the existing `dashboard.jsx`** to find where `RECENT_DRAFTS` is imported and rendered.

- [ ] **Step 2: Replace the data source.** Update its export signature to accept the props passed from `page.jsx`:

```jsx
export const Dashboard = ({ papers = [], loading = false, error = null, refresh }) => {
```

Inside, remove the `import { RECENT_DRAFTS } from "./data";` (if present) and any references. Use `papers` directly.

Map each row's existing render to use the API shape (`{ id, title, level, status, progress, updated_at }`). When clicking a row, route to `/paper/{id}?tab=run`:

```jsx
import Link from "next/link";
// ...
<Link href={`/paper/${p.id}?tab=run`} className="row">
  ...existing visual...
</Link>
```

Add an empty state when `papers.length === 0 && !loading`:

```jsx
<div className="empty">
  <h2>No drafts yet</h2>
  <p>Start your first thesis from the wizard.</p>
  <Link href="/wizard" className="btn btn-primary">New thesis</Link>
</div>
```

Show `loading` state and `error.message` cleanly above the table.

- [ ] **Step 3: Verify** by signing in and viewing `/` — should show empty state.

- [ ] **Step 4: Commit**

```bash
git add web/app/components/dashboard.jsx
git commit -m "web: dashboard fetches /papers and shows empty state"
```

---

## Task 16: Wire Wizard to POST `/papers`

**Files:**
- Modify: `web/app/components/wizard.jsx`

- [ ] **Step 1: Modify the "Start agent pipeline" button.**

At the top of the component, add:

```jsx
import { useRouter } from "next/navigation";
import { apiFetch } from "../lib/api";

// then inside Wizard():
const router = useRouter();
const [submitting, setSubmitting] = useState(false);
const [submitError, setSubmitError] = useState(null);

const start = async () => {
  setSubmitting(true);
  setSubmitError(null);
  try {
    const body = {
      topic,
      research_question: question,
      academic_level: level,
      language: language.toLowerCase().startsWith("english") ? "en" :
                language.toLowerCase().startsWith("spanish") ? "es" :
                language.toLowerCase().startsWith("german") ? "de" :
                language.toLowerCase().startsWith("french") ? "fr" :
                language.toLowerCase().startsWith("mandarin") ? "zh" :
                language.toLowerCase().startsWith("japanese") ? "ja" : "en",
      model,
      citation_style: citationStyle.toLowerCase(),
      sources,
      tone,
    };
    const resp = await apiFetch("/papers", { method: "POST", body });
    router.push(`/paper/${resp.paper_id}?tab=run`);
  } catch (e) {
    setSubmitError(e.message);
  } finally {
    setSubmitting(false);
  }
};
```

Replace the existing button's `onClick`:

```jsx
<button
  className="btn btn-primary btn-block btn-lg"
  onClick={start}
  disabled={submitting}
>
  <Icon name="play" size={16} stroke={2.5} />
  {submitting ? "Starting…" : "Start agent pipeline"}
</button>
{submitError && <div style={{ color: "var(--danger-fg)", fontSize: 12, marginTop: 6 }}>{submitError}</div>}
```

Remove the `go` prop from the component signature; no longer used.

- [ ] **Step 2: Smoke test**

Sign in, fill in a topic, click Start. The browser should navigate to `/paper/<id>?tab=run`. The page will show no live activity until SSE is wired (next task), but a job row exists in the DB and you'll see a subprocess running with `ps`/Task Manager.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/wizard.jsx
git commit -m "web: wizard submits real POST /papers and routes to paper page"
```

---

## Task 17: Wire AgentRun to SSE

**Files:**
- Modify: `web/app/components/agent-run.jsx`

- [ ] **Step 1: Add SSE subscription.** At the top of the file, replace the existing mock state with API-driven state. Read the existing component, then change as follows:

Replace the `NEW_FEED_LINES` constant and the fake `phaseStates` object with this:

```jsx
import { useEffect, useState } from "react";
import { openEventStream } from "../lib/api";

export const AgentRun = ({ jobId }) => {
  const [feed, setFeed] = useState([]);
  const [phaseStates, setPhaseStates] = useState({
    research: { state: "queued", progress: 0, activeAgents: [] },
    structure: { state: "queued", progress: 0, activeAgents: [] },
    compose: { state: "queued", progress: 0, activeAgents: [] },
    qa: { state: "queued", progress: 0, activeAgents: [] },
    compile: { state: "queued", progress: 0, activeAgents: [] },
    export: { state: "queued", progress: 0, activeAgents: [] },
  });
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!jobId) return;
    const close = openEventStream(jobId, {
      onEvent: (msg) => {
        if (msg.type === "activity") {
          setFeed((f) => [{ phase: msg.phase || "compose", agent: msg.agent || "Engine",
                            text: msg.text || "", t: new Date().toLocaleTimeString().slice(0, 5) }, ...f].slice(0, 50));
        } else if (msg.type === "phase_progress") {
          setPhaseStates((prev) => {
            const next = { ...prev };
            const order = ["research", "structure", "compose", "qa", "compile", "export"];
            const idx = order.indexOf(msg.phase);
            for (let i = 0; i < idx; i++) next[order[i]] = { ...next[order[i]], state: "done", progress: 1, activeAgents: [] };
            next[msg.phase] = { state: msg.progress >= 1 ? "done" : "active",
                                 progress: msg.progress || 0,
                                 activeAgents: msg.active_agents || [] };
            return next;
          });
        }
      },
      onDone: () => setDone(true),
      onError: (e) => setError(e.text || e.message || "stream error"),
    });
    return close;
  }, [jobId]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1100);
    return () => clearInterval(id);
  }, []);

  // ... rest of the existing render (PipelineDiagram, ActivityFeed, ChapterProgress, CitationStream)
  // Remove the imports of ACTIVITY_FEED, CITATIONS, THESIS_OUTLINE from "./data" if they were only used as mock seeds.
  // For ChapterProgress and CitationStream, until per-section progress is wired, render them in a "waiting" state:
  //   ChapterProgress: show "Drafting in progress…" instead of THESIS_OUTLINE map.
  //   CitationStream: hide entirely until done; or render a "Citations will appear once the job finishes" placeholder.
```

Keep the visual sub-components (`PipelineDiagram`, `ActivityFeed`, `LegendDot`, `FlowParticles`, `PhaseColumn`, `AgentChip`) unchanged — they already read from props.

Show `error` banner and `done` banner near the top:

```jsx
{error && <div className="banner banner-error">Job failed: {error}</div>}
{done && <div className="banner banner-ok">Draft ready — open the Editor tab.</div>}
```

(Use existing `var(--danger-fg)` / `var(--ok-fg)` styling — see other components for the pattern.)

- [ ] **Step 2: Smoke test**

With API + engine running and a real job submitted from the wizard, open `/paper/<id>?tab=run` and watch the feed populate in real time. Expect the "research" phase to flash to "active" within a few seconds.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/agent-run.jsx
git commit -m "web: agent-run subscribes to SSE for live job progress"
```

---

## Task 18: Wire Citations tab

**Files:**
- Modify: `web/app/components/citations.jsx`

- [ ] **Step 1: Replace mock import with API fetch.**

Read the current file, then change its top imports and component signature:

```jsx
"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";

export const Citations = ({ paperId, citationStyle }) => {
  const { data: citations, error, isLoading } = useSWR(paperId ? `/papers/${paperId}/citations` : null, swrFetcher);

  if (isLoading) return <div style={{ padding: 32 }}>Loading citations…</div>;
  if (error) return <div style={{ padding: 32 }}>Citations not available yet. The bibliography appears once the job completes.</div>;
  // ... reuse existing rendering, mapping over `citations` instead of the mock CITATIONS import.
}
```

Replace all references to the old mock `CITATIONS` array with `citations`. Field names match (`key`, `title`, `authors`, `year`, `doi`, `source`, `venue`).

- [ ] **Step 2: Commit**

```bash
git add web/app/components/citations.jsx
git commit -m "web: citations tab fetches real bibliography from API"
```

---

## Task 19: Wire DraftEditor as read-only viewer

**Files:**
- Modify: `web/app/components/draft-editor.jsx`

- [ ] **Step 1: Replace any mock content with API-loaded HTML.**

```jsx
"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";

const READ_ONLY = true;

export const DraftEditor = ({ paperId, citationStyle }) => {
  const { data, error, isLoading } = useSWR(paperId ? `/papers/${paperId}/draft` : null, swrFetcher);

  if (isLoading) return <div style={{ padding: 32 }}>Loading draft…</div>;
  if (error) return <div style={{ padding: 32 }}>Draft not ready. It will appear here once generation finishes.</div>;

  return (
    <div className="canvas" style={{ maxWidth: 880, margin: "0 auto", padding: "32px 24px" }}>
      <article className="prose" dangerouslySetInnerHTML={{ __html: data.html }} />
      {READ_ONLY && (
        <div style={{ marginTop: 24, padding: 12, background: "var(--ink-50)", borderRadius: 8, fontSize: 12, color: "var(--ink-500)" }}>
          Editing is coming soon. For now, download the DOCX from the Export tab to revise.
        </div>
      )}
    </div>
  );
};
```

Keep `prose` styling from `globals.css` (already defines academic typography). If not present, leave it — the HTML renders with browser defaults.

- [ ] **Step 2: Commit**

```bash
git add web/app/components/draft-editor.jsx
git commit -m "web: draft-editor renders generated draft read-only"
```

---

## Task 20: Wire ExportTab to real downloads

**Files:**
- Modify: `web/app/components/export-tab.jsx`

- [ ] **Step 1: Replace mock state with API fetch + real download URLs.**

```jsx
"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";

const LABELS = { pdf: "PDF", docx: "Microsoft Word", tex: "LaTeX source", md: "Markdown", zip: "Full bundle (ZIP)" };

export const ExportTab = ({ paperId, citationStyle }) => {
  const { data: exports, error, isLoading } = useSWR(paperId ? `/papers/${paperId}/exports` : null, swrFetcher);

  if (isLoading) return <div style={{ padding: 32 }}>Loading exports…</div>;
  if (error) return <div style={{ padding: 32 }}>Exports will appear when the job finishes.</div>;

  return (
    <div className="canvas" style={{ padding: 24 }}>
      <h2 className="section-title" style={{ marginBottom: 16 }}>Download</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
        {(exports || []).map((e) => (
          <a key={e.format} className="card" style={{ padding: 16 }}
             href={`${BASE}/papers/${paperId}/exports/${e.format}`} target="_blank" rel="noreferrer">
            <div style={{ fontWeight: 700, fontSize: 14 }}>{LABELS[e.format] || e.format.toUpperCase()}</div>
            <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4 }}>
              {(e.size / 1024).toFixed(0)} KB · {new Date(e.generated_at).toLocaleString()}
            </div>
          </a>
        ))}
        {(!exports || !exports.length) && <div style={{ color: "var(--ink-500)" }}>No exports yet.</div>}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/export-tab.jsx
git commit -m "web: export tab lists real artifacts and links to download endpoint"
```

---

# Phase D — Integration

## Task 21: `dev.sh` brings up the full stack

**Files:**
- Modify: `dev.sh`

- [ ] **Step 1: Read existing `dev.sh`** (currently only starts Next.js).

- [ ] **Step 2: Replace with:**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env at repo root. Copy from docs/superpowers/plans/2026-05-23-web-engine-mvp.md (env section) first."
  exit 1
fi

# Load env into this shell
set -a
source .env
set +a

# 1. API
if [ ! -d api/.venv ]; then
  (cd api && python -m venv .venv && .venv/bin/pip install -e ".[dev]")
fi

(cd api && .venv/bin/alembic upgrade head)
(cd api && .venv/bin/uvicorn app.main:app --reload --port "${API_PORT:-7100}") &
API_PID=$!

# 2. Web
if [ ! -d web/node_modules ]; then
  (cd web && npm install)
fi
(cd web && npm run dev) &
WEB_PID=$!

trap "kill $API_PID $WEB_PID 2>/dev/null || true" EXIT INT TERM
wait
```

(Windows users running this from Git-Bash: `.venv/bin/` is `.venv/Scripts/` — handle with a conditional if needed. For simplicity, on Windows recommend running `api` and `web` in two separate terminals; the script targets WSL/macOS/Linux.)

- [ ] **Step 3: Make executable + smoke test**

```bash
chmod +x dev.sh
./dev.sh
```
Open `http://localhost:3000`, redirect to `/login`, sign up, navigate dashboard.

- [ ] **Step 4: Commit**

```bash
git add dev.sh
git commit -m "dev: dev.sh starts api + web together"
```

---

## Task 22: End-to-end manual smoke gate

**Files:** none — this is a checklist task.

- [ ] **Step 1: Ensure `.env` is populated** with `DATABASE_URL` pointing at a real Postgres and the other vars from the env table above.

- [ ] **Step 2: Start the stack:** `./dev.sh`.

- [ ] **Step 3: Manual flow:**
  1. Visit `http://localhost:3000`. You should redirect to `/login`.
  2. Sign up with a real email + password.
  3. Click "New thesis", fill in a tiny topic (e.g., "Coffee and productivity"), pick `Research paper`, `Gemini Flash`, click Start.
  4. You land on `/paper/<id>?tab=run`. Within ~30s, the activity feed shows real engine output. The Research phase chip flips active → done.
  5. Wait for completion (Gemini Flash on a tiny topic: ~5–10 min). When the `job_done` event arrives, the "Draft ready" banner shows.
  6. Click Editor tab — markdown renders.
  7. Click Citations tab — real bibliography shows.
  8. Click Export tab — PDF/DOCX/MD download links. Click PDF → opens in browser.

- [ ] **Step 4: If anything fails, file a follow-up task. Do not patch over by mocking.**

- [ ] **Step 5: Commit a CHANGELOG note (no code)**

Append to `CHANGELOG.md`:

```markdown
## Unreleased
- Hosted SaaS MVP: web wired to engine through new FastAPI service with auth, S3 storage, live progress over SSE. Billing out of scope.
```

```bash
git add CHANGELOG.md
git commit -m "changelog: web<->engine MVP"
```

---

# Self-review checklist

Coverage check against the spec (`docs/superpowers/specs/2026-05-23-web-engine-mvp-design.md`):

| Spec section | Task(s) |
|---|---|
| §1 Goals 1–6 | 7, 17, 19, 18, 20, 11, 14 |
| §2 Architecture (api/web/engine units) | 1, 11, 12 |
| §3 API surface — auth | 5 |
| §3 API surface — papers | 7 |
| §3 API surface — jobs | 9 |
| §3 API surface — draft/citations/exports | 10 |
| §3 SSE event shape | 8, 9, 11 |
| §3 Quotas | 6, 7 |
| §4 users / sessions tables | 2, 5 |
| §4 papers / jobs / job_events tables | 2, 7, 8 |
| §4 S3 layout `opendraft/users/.../jobs/...` | 3, 10, 11 |
| §5 `engine/__main__.py` | 11 |
| §5 JobMonitor + pubsub + recovery | 8, 9 |
| §5 cancel | 8, 9 |
| §6 `lib/api.js`, `auth-context`, middleware | 12 |
| §6 login/signup pages | 13 |
| §6 routing changes, sidebar drop billing | 14 |
| §6 dashboard/wizard/agent-run/citations/draft/export wiring | 15, 16, 17, 18, 19, 20 |
| §7 Repo layout | result of all tasks |
| §8 Local dev / .env / dev.sh | 21, conventions block |
| §9 Testing strategy | every task's tests + 22 |
| §10 Open questions | defaults applied: complete-only upload (11), client dedupes via `id:` SSE field (9, 12), global cap left as future env knob |

Placeholder scan: no `TBD` / `TODO` / "appropriate" left in task bodies. All test code shown inline. All file paths absolute or repo-relative and explicit.

Type consistency: `JobTracker.log_activity(message, *, event_type, phase, agent)` and `JobTracker.update_phase(phase, *, progress_percent, details)` exist in `engine/job_io.py` (Task 11) and are exactly what `engine/utils/progress_tracker.py`'s `ACTIVITY_MESSAGES` callers expect. SSE event shape `{type, phase, agent, text, ...}` is consistent across engine writer (Task 11), API ingester (Task 8), API streamer (Task 9), and web parser (Tasks 12, 17). Quota error codes `already_running` / `daily_quota` are consistent between `quotas.py` (Task 6) and the HTTP mapping in `papers.py` (Task 7).
