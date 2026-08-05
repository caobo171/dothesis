"""tool_runs — keep the run's input/output .docx, and its live progress.

The tool history could say "-89 credit" and nothing else. Nothing was kept: the
table stored counts only and /document/humanize streamed the .docx back without
persisting it, so a student who closed the tab had lost the document they paid
for and support could not see what a bad run produced.

Files are kept 30 days (tool_artifacts.FILE_RETENTION_DAYS) and removed by
scripts/purge_tool_run_files.py, which nulls these columns and KEEPS the row —
the run is a billing record and has to outlive the file it points at.

The three progress columns ride along rather than taking a migration of their
own: the row is now written before the work starts so a poll can report "batch
12 of 70" while the request is still open. `status` defaults to "done" so every
row that predates this reads as a finished run, not a stuck one.

Revision ID: 20260805_toolartifact01
Revises: 20260805_toolruns01
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260805_toolartifact01"
down_revision = "20260805_toolruns01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_runs", sa.Column("input_s3_uri", sa.Text(), nullable=True))
    op.add_column("tool_runs", sa.Column("output_s3_uri", sa.Text(), nullable=True))
    op.add_column("tool_runs", sa.Column("input_filename", sa.String(255), nullable=True))
    op.add_column("tool_runs", sa.Column("files_expire_at",
                                         sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_runs", sa.Column("parent_run_id", sa.BigInteger(), nullable=True))
    op.add_column("tool_runs", sa.Column("metrics", postgresql.JSONB(), nullable=True))
    op.add_column("tool_runs", sa.Column("status", sa.String(16), nullable=False,
                                         server_default="done"))
    op.add_column("tool_runs", sa.Column("progress_done", sa.Integer(), nullable=False,
                                         server_default="0"))
    op.add_column("tool_runs", sa.Column("progress_total", sa.Integer(), nullable=False,
                                         server_default="0"))
    op.create_foreign_key("fk_tool_runs_parent", "tool_runs", "tool_runs",
                          ["parent_run_id"], ["id"], ondelete="SET NULL")
    # The purge job's only query: rows past expiry that still hold a file.
    op.create_index("ix_tool_runs_files_expire_at", "tool_runs", ["files_expire_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_files_expire_at", table_name="tool_runs")
    op.drop_constraint("fk_tool_runs_parent", "tool_runs", type_="foreignkey")
    for col in ("progress_total", "progress_done", "status", "metrics",
                "parent_run_id", "files_expire_at", "input_filename",
                "output_s3_uri", "input_s3_uri"):
        op.drop_column("tool_runs", col)
