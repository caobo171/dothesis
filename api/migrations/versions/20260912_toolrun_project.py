"""tool_runs.project_id — which runs were work inside a thesis project

The Tool usage screen answers "what did I run outside a thesis project", and it
was answering it with every row the user had. The mid-journey import opens run
rows for its own reconstruction walk and its follow-up literature search, purely
so the screen has something to poll, and both landed in the student's history
spelled as raw slugs (`backfill-modules`, `citation-search`) with no label, no
re-run and nothing to act on.

Nullable, no backfill, no default: NULL means standalone, which is what every
row written before today is treated as. The rows that ARE stale — the two slugs
above — cannot be re-linked to their project from anything else on the row, so
they are filtered by name instead (app/tool_billing.PROJECT_ONLY_TOOLS).

ondelete SET NULL rather than CASCADE: this table is a billing record and must
outlive the project it was run against. A deleted project drops a run back into
the standalone history, which is a far better outcome than deleting the invoice.

Revision ID: 20260912_toolrunproj01
Revises: 20260909_blogtrkey01
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260912_toolrunproj01"
down_revision = "20260909_blogtrkey01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_runs",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tool_runs_project_id", "tool_runs", "projects",
        ["project_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_tool_runs_project_id", "tool_runs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_project_id", table_name="tool_runs")
    op.drop_constraint("fk_tool_runs_project_id", "tool_runs", type_="foreignkey")
    op.drop_column("tool_runs", "project_id")
