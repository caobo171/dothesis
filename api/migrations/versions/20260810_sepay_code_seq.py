"""sequence behind the short SePay payment codes (DTS1000, DTS1001, …)

SePay memos moved from PREFIX + 16 hex chars of the order UUID to a short
serial, because the code is retyped by hand into a banking app and is what
SePay's own code-detection config matches on. Sequence rather than a column
default so only bank-transfer orders consume a number.

Starts at 1000 so every code is at least 4 digits — no DTS1/DTS12 that a
truncated bank content could collide with.

Revision ID: 20260810_sepaycodeseq01
Revises: 20260805_toolartifact01
Create Date: 2026-08-10
"""
from alembic import op

revision = "20260810_sepaycodeseq01"
down_revision = "20260805_toolartifact01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS sepay_code_seq START WITH 1000")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS sepay_code_seq")
