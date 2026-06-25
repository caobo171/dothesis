"""create user_memory (per-user cross-project preferences)

4th memory tier above context_store. Holds ONLY whitelisted preferences
(language, citation_style, research_approach, field, …) — never thesis content
or citations. One row per user (user_id PK). See
docs/architecture/2026-06-24-cross-project-user-memory.md.

Revision ID: 20260625_usermem01
Revises: 20260625_thnameauto01
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260625_usermem01"
down_revision = "20260625_thnameauto01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_memory",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "prefs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_memory")
