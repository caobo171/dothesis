"""add projects.focus + projects.module_status

Brief §1.4 — separate `focus` (conversation focus, fluid per message) from
`module_status` (per-module workflow state). Implements PR #1 of the target
architecture (docs/architecture/2026-06-03-researchflow-target-architecture.md
§1 + §7). No behavior change in this PR — columns are added and backfilled;
the chat router still routes on current_module. PR #2 makes focus canonical.

Revision ID: 20260603_focus01
Revises: 20260530_target01
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260603_focus01"
down_revision = "20260530_target01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # focus = conversation focus (brief §1.4). Nullable so legacy projects
    # don't need a non-null default at insert time — callers fall back to
    # current_module when NULL during the dual-write window.
    op.add_column(
        "projects",
        sa.Column("focus", sa.String(8), nullable=True),
    )

    # module_status = JSONB map ModuleId → ('locked'|'in_progress'|'done'|'needs_review').
    # Brief §1.4 calls this "workflow state, bookkeeping". Derived from
    # context_store via orchestrator.state.compute_status_map and persisted
    # here for fast UI reads. Default '{}' so handler code that calls
    # .get(M, 'locked') stays valid before any turn has run on a project.
    op.add_column(
        "projects",
        sa.Column(
            "module_status",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Backfill focus from current_module — best-available default for live
    # projects (matches today's routing). module_status is left as '{}'
    # because the orchestrator recomputes it from context_store on the next
    # turn via compute_status_map; mirroring that derivation in SQL would
    # duplicate the source of truth and drift as DoD validators evolve.
    op.execute("UPDATE projects SET focus = current_module WHERE focus IS NULL")


def downgrade() -> None:
    op.drop_column("projects", "module_status")
    op.drop_column("projects", "focus")
