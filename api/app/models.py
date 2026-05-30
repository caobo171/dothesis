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
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    email_verified: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    google_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verify_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    model_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="standard", server_default="standard")
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
    # Nullable: orchestrator runs (mode="auto") are project-scoped and have no paper_id.
    # Legacy engine jobs always set paper_id; the NOT NULL constraint is dropped in the
    # orchestrator migration so both row types can coexist in the same table.
    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    phase: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    pid: Mapped[int | None] = mapped_column(Integer)
    workdir: Mapped[str | None] = mapped_column(Text)
    events_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Resume state: latest checkpoint JSON written by the engine after a phase boundary.
    # Lets us spin up a fresh job from where this one stopped, even if the workdir is gone.
    checkpoint_json: Mapped[dict | None] = mapped_column(JSONB)
    completed_phase: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)
    # Orchestrator-mode extensions (sub-project 1). All nullable so legacy engine
    # jobs (with mode IS NULL) keep working unchanged. New orchestrator runs set
    # mode = "auto" and populate the other three.
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    mode: Mapped[str | None] = mapped_column(String(16))
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text)


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


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    package_id: Mapped[str] = mapped_column(String(64), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD", server_default="USD")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    polar_checkout_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    polar_order_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(16))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    cta_label: Mapped[str | None] = mapped_column(String(64))
    cta_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Orchestrator tables (sub-project 1)
# ---------------------------------------------------------------------------

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
    # When set (an artifact key like "analysis"), this thread targets that
    # deliverable: the planner routes toward it on the first turn (enter-at-any-
    # step). Seeded once into the graph state, then owned by the checkpoint.
    target_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
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


# ---------------------------------------------------------------------------
# M2 upload tables (sub-project 2)
# ---------------------------------------------------------------------------

class PaperUpload(Base):
    __tablename__ = "paper_uploads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_extract_uri: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
