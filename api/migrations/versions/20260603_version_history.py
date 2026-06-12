"""add version_history table

Brief §2 — append-only snapshots of context_store slices written on each
mutate. Captured by orchestrator.loader.persist_turn (PR #6).

Revision ID: 20260603_vhist01
Revises: 20260603_token01
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260603_vhist01"
down_revision = "20260603_token01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Append-only — no UPDATE/DELETE in app code. The PK is a bigint so a
    # high-write project (many mutates over weeks) doesn't blow through
    # an int4 sequence.
    op.create_table(
        "version_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # slice_field IS the module owning the change ('m1_topic', ...).
        # Stored separately from the snapshot blob so a planner can
        # filter by module without parsing JSONB.
        sa.Column("slice_field", sa.String(32), nullable=False, index=True),
        # slice_after = the slice value AFTER the mutate. We DON'T store
        # 'before' because the previous row of the same (project_id,
        # slice_field) IS the before; storing both would double JSONB
        # bytes for no read advantage.
        sa.Column("slice_after", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("version_history")
