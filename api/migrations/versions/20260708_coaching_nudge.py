"""coaching blob + projects.last_nudge_at

F0 foundation fix: the DB-backed context store (DbProjectStateStore) only
round-trips columns that already exist on `context_store` — any new
context_store key silently drops on save unless it lands in one of the
explicit columns. `coaching` is the catch-all home for project-scoped
coaching/memory keys that don't belong to any single module (m1_topic..
m5_writing). `projects.last_nudge_at` (F11) tracks the last proactive
coaching nudge sent for a project so the nudge scheduler can rate-limit
without a separate table. This migration only adds the columns; wiring
the store to read/write them is a later task.

Revision ID: 20260708_coachnudge01
Revises: 20260630_expscope01
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260708_coachnudge01"
down_revision = "20260630_expscope01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_store",
        sa.Column("coaching", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("last_nudge_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "last_nudge_at")
    op.drop_column("context_store", "coaching")
