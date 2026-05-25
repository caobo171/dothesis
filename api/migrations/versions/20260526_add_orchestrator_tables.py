"""add orchestrator tables (projects, threads, messages, context_store) and extend jobs

Revision ID: 20260526_orch01
Revises: cbab05df531a
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260526_orch01"
down_revision = "cbab05df531a"
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
    # Allow paper_id to be NULL for orchestrator runs (auto-mode jobs are project-scoped,
    # not paper-scoped). Legacy engine rows always have a paper_id set.
    op.alter_column("jobs", "paper_id", existing_type=UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    op.alter_column("jobs", "paper_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.drop_column("jobs", "langgraph_thread_id")
    op.drop_column("jobs", "mode")
    op.drop_column("jobs", "thread_id")
    op.drop_column("jobs", "project_id")
    op.drop_table("context_store")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("projects")
