"""multi-provider payments: provider + paypal/sepay columns on orders

Adds the columns needed to run PayPal and SePay alongside Polar:
- provider (polar|paypal|sepay), defaulting existing rows to polar
- paypal_order_id
- sepay_memo (indexed) + amount_vnd
- external_txn_id (unique) — grant idempotency key for PayPal capture id /
  SePay referenceCode

Revision ID: 20260614_pay01
Revises: 20260614_qidx01
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20260614_pay01"
down_revision = "20260614_qidx01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column(
        "provider", sa.String(16), nullable=False, server_default="polar"))
    op.add_column("orders", sa.Column("paypal_order_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("sepay_memo", sa.String(40), nullable=True))
    op.add_column("orders", sa.Column("amount_vnd", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("external_txn_id", sa.String(128), nullable=True))
    op.create_index("ix_orders_sepay_memo", "orders", ["sepay_memo"])
    op.create_unique_constraint("uq_orders_external_txn_id", "orders", ["external_txn_id"])


def downgrade() -> None:
    op.drop_constraint("uq_orders_external_txn_id", "orders", type_="unique")
    op.drop_index("ix_orders_sepay_memo", table_name="orders")
    op.drop_column("orders", "external_txn_id")
    op.drop_column("orders", "amount_vnd")
    op.drop_column("orders", "sepay_memo")
    op.drop_column("orders", "paypal_order_id")
    op.drop_column("orders", "provider")
