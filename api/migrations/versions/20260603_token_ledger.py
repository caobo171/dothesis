"""add token_ledger table

Brief §1.8 — token meter at the LLM call boundary. Each metered call
inserts one row (project_id, action_kind, model, prompt/completion tokens,
reserved estimate, duration). Aggregates feed the per-action pricing
table.

PR #3 of the target architecture (docs/architecture/2026-06-03-researchflow-
target-architecture.md §5).

Revision ID: 20260603_token01
Revises: 20260603_focus01
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260603_token01"
down_revision = "20260603_focus01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No FK back to projects.id — project_id is nullable here because evals
    # and intake assess calls go through the meter without a project. We
    # also want ledger rows to survive a project DELETE for cost forensics
    # (the row is a historical record, not active state). A soft pointer
    # is enough; aggregations join via project_id in application code.
    op.create_table(
        "token_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("action_kind", sa.String(64), nullable=False, index=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False),
        sa.Column("completion_tokens", sa.Integer, nullable=False),
        # reserved is the pre-call estimate (chars / 4). delta is computed
        # by callers as (prompt + completion) - reserved — not stored to
        # keep INSERT cost low; aggregates compute it on read.
        sa.Column("reserved", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("token_ledger")
