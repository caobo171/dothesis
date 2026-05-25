"""auth_verify_google

Revision ID: cbab05df531a
Revises: 35f297a99bf6
Create Date: 2026-05-25 21:03:23.109129

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cbab05df531a"
down_revision: Union[str, None] = "35f297a99bf6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill username for any rows missing one BEFORE applying NOT NULL/UNIQUE.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, email FROM users WHERE username IS NULL")).all()
    import random, re
    used = {r[0] for r in bind.execute(sa.text("SELECT username FROM users WHERE username IS NOT NULL"))}
    for uid, email in rows:
        prefix = re.sub(r"[^a-zA-Z0-9]", "", (email or "user").split("@")[0])[:24] or "user"
        for _ in range(50):
            candidate = f"{prefix}{random.randint(1000, 9999)}"
            if candidate not in used:
                break
        used.add(candidate)
        bind.execute(
            sa.text("UPDATE users SET username = :u WHERE id = :id"),
            {"u": candidate, "id": uid},
        )

    op.alter_column("users", "username", existing_type=sa.String(64), nullable=False)
    op.create_unique_constraint("users_username_key", "users", ["username"])

    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("google_id", sa.String(64)))
    op.create_unique_constraint("users_google_id_key", "users", ["google_id"])
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("last_verify_sent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "last_verify_sent_at")
    op.drop_column("users", "last_login")
    op.drop_constraint("users_google_id_key", "users", type_="unique")
    op.drop_column("users", "google_id")
    op.drop_column("users", "email_verified")
    op.drop_constraint("users_username_key", "users", type_="unique")
    op.alter_column("users", "username", existing_type=sa.String(64), nullable=True)
