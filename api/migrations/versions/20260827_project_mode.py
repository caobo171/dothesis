"""persisted generation mode on projects (auto vs chat)

Auto Thesis vs guided chat used to be a one-shot sessionStorage flag consumed on
the chat surface's first mount, so it never survived a reload or a return visit —
reopening an Auto Thesis project fell back to plain chat and dropped the
credit/estimate gate. This makes the mode a durable column so it is a property of
the project/goal, chosen once at creation.

Nullable with no server_default: existing projects stay NULL (the client reads
NULL as "chat"), and only new projects created through the updated /projects
route carry an explicit "auto"/"chat".

Revision ID: 20260827_projectmode01
Revises: 20260810_sepaycodeseq01
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "20260827_projectmode01"
down_revision = "20260810_sepaycodeseq01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("mode", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "mode")
