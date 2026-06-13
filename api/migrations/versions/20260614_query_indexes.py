"""composite indexes for hot read paths: messages + job_events

The two highest-traffic, highest-growth read patterns both filter by a parent id
and then order/range on the row id:

- messages: list_messages (keyset pagination, ORDER BY id DESC), the orchestrator
  loader's full-transcript load (ORDER BY id), and per-thread cost sums — all
  WHERE thread_id = X.
- job_events: SSE polling fires WHERE job_id = X AND id > since ORDER BY id
  repeatedly for the duration of a run.

A single-column FK index forces a filter-then-sort; the composite (parent_id, id)
serves both the equality filter and the ordered range as one index scan. Because
the composite has the FK column as its leftmost prefix, it fully supersedes the
existing single-column index, which we drop to avoid double write/storage cost.

Revision ID: 20260614_qidx01
Revises: 20260613_msgcost01
Create Date: 2026-06-14
"""
from alembic import op

revision = "20260614_qidx01"
down_revision = "20260613_msgcost01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_messages_thread_id_id", "messages", ["thread_id", "id"])
    op.drop_index("ix_messages_thread_id", table_name="messages")

    op.create_index("ix_job_events_job_id_id", "job_events", ["job_id", "id"])
    op.drop_index("ix_job_events_job_id", table_name="job_events")


def downgrade() -> None:
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.drop_index("ix_job_events_job_id_id", table_name="job_events")

    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])
    op.drop_index("ix_messages_thread_id_id", table_name="messages")
