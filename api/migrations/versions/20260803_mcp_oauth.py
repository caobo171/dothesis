"""MCP connector OAuth — registered clients, auth codes, refresh tokens.

These tables back mcp/oauth.py, the OAuth 2.1 façade that lets Claude/ChatGPT
add DoThesis as a connector. They started life in a separate SQLite file next to
the MCP process; this migration is that move, and the reason is that the data is
not private to that process:

- "how many students connected Claude?" is a campaign metric (mcp/MCP_OAUTH_PLAN
  .md item 6) and needs to be a query, not an SSH session;
- a "Disconnect" button in DoThesis's own UI needs the API to SEE these grants
  (routers/connectors.py), which it cannot do across a process-local file;
- a foreign key to users means deleting an account takes its connector grants
  with it instead of orphaning them.

The MCP process still never imports app.* — it reaches these tables with plain
psycopg. Separate PROCESS, shared DATABASE.

Nothing is migrated FROM the old SQLite file: it only ever held clients from a
local test run, and re-registering is one click in the AI client. Delete
mcp/oauth.db if a deploy left one behind.

Revision ID: 20260803_mcpoauth01
Revises: 20260715_partnertok01
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260803_mcpoauth01"
down_revision = "20260715_partnertok01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.Text(), primary_key=True),
        # NULL for public (PKCE-only) clients, which is what Claude registers
        # as. A SHA-256 digest when present — never the secret itself.
        sa.Column("secret_hash", sa.Text(), nullable=True),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "mcp_oauth_codes",
        # The code itself is never stored: it rides in a redirect URL, so the
        # copy at rest must not be replayable.
        sa.Column("code_hash", sa.Text(), primary_key=True),
        sa.Column("client_id", sa.Text(),
                  sa.ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_mcp_oauth_codes_user_id", "mcp_oauth_codes", ["user_id"])
    # The sweep deletes by expiry on every write; without this it degrades into
    # a sequential scan once the table has any history.
    op.create_index("ix_mcp_oauth_codes_expires_at", "mcp_oauth_codes", ["expires_at"])

    op.create_table(
        "mcp_oauth_refresh_tokens",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column("client_id", sa.Text(),
                  sa.ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Both lookups the connector UI needs: "this user's grants" (list/revoke)
    # and the expiry sweep.
    op.create_index("ix_mcp_oauth_refresh_user_id",
                    "mcp_oauth_refresh_tokens", ["user_id"])
    op.create_index("ix_mcp_oauth_refresh_expires_at",
                    "mcp_oauth_refresh_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_oauth_refresh_expires_at", table_name="mcp_oauth_refresh_tokens")
    op.drop_index("ix_mcp_oauth_refresh_user_id", table_name="mcp_oauth_refresh_tokens")
    op.drop_table("mcp_oauth_refresh_tokens")
    op.drop_index("ix_mcp_oauth_codes_expires_at", table_name="mcp_oauth_codes")
    op.drop_index("ix_mcp_oauth_codes_user_id", table_name="mcp_oauth_codes")
    op.drop_table("mcp_oauth_codes")
    op.drop_table("mcp_oauth_clients")
