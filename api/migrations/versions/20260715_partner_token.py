"""jobs.partner_token — durable partner progress-token -> Job mapping.

The partner report path becomes an ordinary Job (headless convergence spec §3);
its progress poll needs token -> job resolution that survives restarts and
multiple API processes, which the old in-memory _PROGRESS dict did not.

Nullable: every existing jobs row predates partner tokens, and non-partner runs
never get one. Indexed: the token is the lookup key for the progress endpoint.

UNIQUE, because the token is caller-supplied and partner auth is one global
shared secret with no partner-id claim (routers/partner_report.py) — so two
partners can hand us the same token, and a non-unique index would let the
progress lookup silently return the other partner's Job. Unique turns that
crossover into an IntegrityError at insert that the write path must handle
(mint server-side / regenerate / 409) instead of leaking. Postgres treats NULLs
as distinct, so this does not conflict with the column staying nullable.

Revision ID: 20260715_partnertok01
Revises: 20260715_paperupmime01
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260715_partnertok01"
down_revision = "20260715_paperupmime01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("partner_token", sa.Text(), nullable=True))
    op.create_index("ix_jobs_partner_token", "jobs", ["partner_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_jobs_partner_token", table_name="jobs")
    op.drop_column("jobs", "partner_token")
