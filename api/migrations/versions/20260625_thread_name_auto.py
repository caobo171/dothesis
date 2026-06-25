"""add threads.name_auto

Flags a thread whose name was auto-generated (from M1 research_title or a
one-shot cheap LLM summary). False by default so a hand-set name is never
overwritten by the namer. Nullable-with-default keeps existing rows valid.

Revision ID: 20260625_thnameauto01
Revises: 20260614_pay01
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260625_thnameauto01"
down_revision = "20260614_pay01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("name_auto", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("threads", "name_auto")
