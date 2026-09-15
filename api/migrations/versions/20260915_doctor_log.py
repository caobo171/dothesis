"""add doctor repair ledger to context_store

Revision ID: 20260915_doctorlog01
Revises: 20260915_m5canon01
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260915_doctorlog01"
down_revision = "20260915_m5canon01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A sibling of `coaching`, deliberately NOT inside a module slice: slices
    # hold the student's work, and a diagnostic ledger is not that. Keeping it
    # out also keeps it clear of SLICE_OWNERSHIP, which decides what
    # commit_slice is allowed to overwrite.
    op.add_column(
        "context_store",
        sa.Column("doctor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("context_store", "doctor")
