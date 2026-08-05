"""tool_runs — one row per standalone tool invocation, billed or not.

The tools (humanize, cite a .docx, check a reference list, writing rhythm) had
no record of their own. An LLM-backed one left a `token_ledger` row, but every
row said action_kind="humanize" whatever it actually was, and the tools that
call no model — CrossRef lookups, stylometry — left nothing at all. So "how much
is the citation tool being used, by whom, and is it working?" was unanswerable,
and every deterministic tool ran for free without anyone deciding it should.

Deliberately a SEPARATE table from token_ledger rather than more rows in it:
token_ledger is per metered LLM call (several per run, one per model) and this
is per RUN. Joining them for "what did this cost the student" is the point.

Kept when the run FAILS, and when it charges zero — a tool that is being used
heavily for free is exactly the thing this exists to surface.

Sizes, never prose. Same line mcp_tool_calls draws, for the same reason: an
audit log that accumulates copies of students' theses is a liability.

Revision ID: 20260805_toolruns01
Revises: 20260803_ledgeruser01
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260805_toolruns01"
down_revision = "20260803_ledgeruser01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Which door the call came through. The same tool is reachable from the
        # web app, the partner API and the MCP connector, and "who is actually
        # using this" is a different answer per surface.
        sa.Column("surface", sa.String(16), nullable=False, server_default="web"),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        # What was billed BY COUNT — references checked, sources looked up.
        # Zero for token-billed tools, which is how the two schemes are told
        # apart after the fact.
        sa.Column("units", sa.Integer(), nullable=False, server_default="0"),
        # Both numbers, on purpose. Charging is capped at the balance (a student
        # at zero is under-billed rather than refused, matching auto runs), and
        # a table that only recorded what was collected would hide exactly how
        # much is being given away.
        sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    # The admin view lists recent runs newest-first and drills down by user;
    # the composite serves the drill-down, matching mcp_tool_calls.
    op.create_index("ix_tool_runs_created_at", "tool_runs", ["created_at"])
    op.create_index("ix_tool_runs_user_created", "tool_runs", ["user_id", "created_at"])
    op.create_index("ix_tool_runs_tool", "tool_runs", ["tool"])
    op.create_index("ix_tool_runs_ok", "tool_runs", ["ok"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_ok", table_name="tool_runs")
    op.drop_index("ix_tool_runs_tool", table_name="tool_runs")
    op.drop_index("ix_tool_runs_user_created", table_name="tool_runs")
    op.drop_index("ix_tool_runs_created_at", table_name="tool_runs")
    op.drop_table("tool_runs")
