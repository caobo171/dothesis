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
    text,
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
    # Partner runs: the caller-supplied opaque progress_token, so the
    # /partner/report/progress poll can find this Job. Durable + multi-process,
    # unlike the in-memory _PROGRESS dict it replaces (convergence spec §3).
    # Nullable because only mode="partner" rows carry a token; indexed because
    # the token is the only key the progress poll has to look the Job up by.
    # Unique because the token is caller-supplied and partner auth is a single
    # global shared secret with no partner-id claim, so two partners can send
    # the same token — without uniqueness the poll would silently resolve to
    # whichever row Postgres returned first, handing one partner another's
    # progress. Unique makes that collision a loud IntegrityError at insert.
    # Postgres counts NULLs as distinct, so unique + nullable coexist.
    partner_token: Mapped[str | None] = mapped_column(Text, index=True, unique=True)


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
    # Which checkout provider owns this order: polar | paypal | sepay. Defaults to
    # polar so pre-existing rows (all Polar) read correctly.
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="polar", server_default="polar")
    polar_checkout_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    polar_order_id: Mapped[str | None] = mapped_column(String(128))
    # PayPal order id (returned by create-order; the approval/capture key).
    paypal_order_id: Mapped[str | None] = mapped_column(String(64))
    # SePay: the unique transfer memo we ask the user to put in their bank
    # transfer, and the VND amount due (rounded from the USD package price).
    sepay_memo: Mapped[str | None] = mapped_column(String(40), index=True)
    amount_vnd: Mapped[int | None] = mapped_column(Integer)
    # Provider txn id used for grant idempotency (PayPal capture id / SePay
    # referenceCode). Unique so a re-delivered webhook can't double-credit.
    external_txn_id: Mapped[str | None] = mapped_column(String(128), unique=True)
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


class UserMemory(Base):
    """Per-user cross-project memory (4th tier above context_store).

    Stores ONLY durable preferences / meta-patterns — never thesis content,
    citations, or numeric results (that would leak across projects and violate
    DoThesis's anti-fabrication invariant). Allowed keys are hard-whitelisted in
    app.user_memory.USER_MEMORY_KEYS. One row per user (1:1).

    `prefs` shape: { <key>: {"value": ..., "source_project_id": str|None,
                             "confidence": float, "updated_at": iso8601} }
    """
    __tablename__ = "user_memory"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    # Brief §1.4 — conversation focus, separate from current_module. Nullable
    # during the dual-write window (PR #1): callers fall back to current_module
    # when focus is NULL. PR #2's router rewrite makes focus canonical and
    # demotes current_module to a shadow column scheduled for removal.
    focus: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Brief §1.4 — per-module workflow status map. JSONB Dict[ModuleId, str]
    # where str ∈ {locked, in_progress, done, needs_review}. Derived from
    # context_store via orchestrator.state.compute_status_map and persisted
    # here for fast UI reads — NEVER the source of truth.
    module_status: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # F11 — last time a proactive coaching nudge was sent for this project.
    # Nullable: most projects have never received one. Lets the nudge
    # scheduler rate-limit without a separate table.
    last_nudge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Export(Base):
    """A generated export document — module-agnostic.

    Exports used to live inside `m5_writing.export_artifacts`, which made a
    per-module export (e.g. "M3 design") wrongly appear under M5 Writing. They're
    now first-class: each row records WHAT was exported via `scope` ("full" for a
    whole thesis, or "M1".."M4" for a single module) so the UI can list them in a
    dedicated Exports area and label each correctly. One row per artifact
    (a docx and its pdf are two rows sharing the same scope + created_at-ish).
    """
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # "full", a single module ("M3"), or a comma-joined set ("M1,M3,M4").
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="full")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # docx | pdf
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, server_default="Main")
    # True once the thread name was auto-generated (from M1 research_title or a
    # one-shot cheap LLM summary of the first message). Guards against (a) the
    # namer re-running every turn and (b) overwriting a name the user set by hand
    # — a manual rename leaves this False, so the namer skips it forever.
    name_auto: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
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
    # Per-response cost + latency (assistant rows). Shown in the message footer
    # and summed for thread/project totals. Default 0 so user rows and legacy
    # rows are valid.
    cost_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_extract_uri: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TokenLedger(Base):
    """Brief §1.8 — one row per metered LLM call. Powers the per-action
    pricing table and cost forensics. No FK back to projects so rows
    survive a project DELETE (historical record, not active state).
    """
    __tablename__ = "token_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class VersionHistory(Base):
    """Brief §2 — append-only snapshots of context_store slice writes.

    One row per mutate. The previous row for the same (project_id,
    slice_field) IS the 'before' value, so we only persist 'after' —
    halves JSONB bytes for the same read semantics.
    """
    __tablename__ = "version_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    slice_field: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    slice_after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
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
    # Home for project-scoped coaching/memory keys that don't belong to any
    # single module column above (e.g. advisor-feedback tracking, nudge
    # state) — the DB-backed store only round-trips known columns, so a new
    # context_store key with nowhere to live gets silently dropped in prod.
    coaching: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
