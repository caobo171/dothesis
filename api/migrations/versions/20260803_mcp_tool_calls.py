"""mcp_tool_calls — audit trail for MCP connector usage.

Before this, the only record of a connector call was the MCP process's uvicorn
access line ("POST /mcp 200"), which names neither the user nor the tool and is
rotated away by journald. So "who connected Claude?" was answerable and "who
used it, how much, did it work?" was not — the second being the one that matters
for the giveaway campaign (MCP_OAUTH_PLAN.md item 6) and for spotting abuse.

Stores sizes, never the prose. See the model docstring in api/app/models.py for
why that line is drawn deliberately rather than by omission.

Revision ID: 20260803_mcptoolcall01
Revises: 20260803_mcpoauth01
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260803_mcptoolcall01"
down_revision = "20260803_mcpoauth01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Intentionally NOT a foreign key: de-registering a client must not be
        # able to fail, or cascade away, an audit row.
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    # The admin view's default is "recent calls, newest first", and the per-user
    # drill-down filters by user then sorts by time — hence the composite.
    op.create_index("ix_mcp_tool_calls_created_at", "mcp_tool_calls", ["created_at"])
    op.create_index("ix_mcp_tool_calls_user_created", "mcp_tool_calls",
                    ["user_id", "created_at"])
    op.create_index("ix_mcp_tool_calls_tool", "mcp_tool_calls", ["tool"])
    op.create_index("ix_mcp_tool_calls_ok", "mcp_tool_calls", ["ok"])


def downgrade() -> None:
    op.drop_index("ix_mcp_tool_calls_ok", table_name="mcp_tool_calls")
    op.drop_index("ix_mcp_tool_calls_tool", table_name="mcp_tool_calls")
    op.drop_index("ix_mcp_tool_calls_user_created", table_name="mcp_tool_calls")
    op.drop_index("ix_mcp_tool_calls_created_at", table_name="mcp_tool_calls")
    op.drop_table("mcp_tool_calls")
