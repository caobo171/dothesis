"""retire the needs_review module status in favour of a non-blocking stale flag

`needs_review` was a fourth value in projects.module_status. It outranked `done`,
so editing an upstream module DEMOTED every finished module below it and the
roadmap then routed the student back to re-check them before anything else could
move forward. The product rule is the opposite — hand the student output they can
fine-tune afterwards — so invalidation stops being a workflow status.

Existing rows are not thrown away: every module currently sitting at
`needs_review` was `done` before something upstream changed, so it is rewritten
to `done` and its id is recorded in the new `stale_modules` list. The student
keeps the information ("this may be out of date") and loses the gate.

Revision ID: 20260903_dropneedsreview01
Revises: 20260827_projectmode01
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260903_dropneedsreview01"
down_revision = "20260827_projectmode01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("stale_modules", postgresql.JSONB(),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    # Carry the flag across before erasing it: the keys whose value is
    # 'needs_review' become the stale list, and those entries flip back to
    # 'done'. jsonb_object_agg over the existing map rebuilds it in one pass;
    # the FILTER'd aggregate collects the ids. Rows with no needs_review entry
    # are untouched (the WHERE keeps this off the whole table).
    op.execute(
        """
        UPDATE projects p
        SET stale_modules = COALESCE(s.stale, '[]'::jsonb),
            module_status = COALESCE(s.status, p.module_status)
        FROM (
            SELECT p2.id,
                   jsonb_agg(e.key ORDER BY e.key)
                       FILTER (WHERE e.value = '"needs_review"'::jsonb) AS stale,
                   jsonb_object_agg(
                       e.key,
                       CASE WHEN e.value = '"needs_review"'::jsonb
                            THEN '"done"'::jsonb ELSE e.value END
                   ) AS status
            FROM projects p2, jsonb_each(p2.module_status) e
            GROUP BY p2.id
        ) s
        WHERE p.id = s.id
          AND p.module_status::text LIKE '%needs_review%'
        """
    )


def downgrade() -> None:
    # Fold the stale list back into module_status as needs_review, then drop the
    # column — so a downgrade lands on the same data the upgrade started from.
    op.execute(
        """
        UPDATE projects p
        SET module_status = p.module_status || s.patch
        FROM (
            SELECT p2.id, jsonb_object_agg(m.value, '"needs_review"'::jsonb) AS patch
            FROM projects p2, jsonb_array_elements_text(p2.stale_modules) m
            GROUP BY p2.id
        ) s
        WHERE p.id = s.id AND jsonb_array_length(p.stale_modules) > 0
        """
    )
    op.drop_column("projects", "stale_modules")
