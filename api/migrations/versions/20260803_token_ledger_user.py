"""token_ledger.user_id — attribute project-less metered calls to a person.

`humanize` runs without a project (it takes a passage, not a thesis), so even
once it was metered there was no way to answer "who incurred this cost?" — the
ledger could only be grouped by project. Every humanize row would have been
project_id NULL and anonymous.

Nullable, and deliberately NOT a foreign key, matching `project_id` on the same
table: the model docstring calls this a historical record that must outlive a
project DELETE, and the same reasoning applies to a deleted account. Cost
forensics for a month that has already been paid for should not disappear
because someone closed their account.

Revision ID: 20260803_ledgeruser01
Revises: 20260803_mcptoolcall01
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260803_ledgeruser01"
down_revision = "20260803_mcptoolcall01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("token_ledger",
                  sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_token_ledger_user_id", "token_ledger", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_token_ledger_user_id", table_name="token_ledger")
    op.drop_column("token_ledger", "user_id")
