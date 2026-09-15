"""collapse legacy six-chapter final_sections into the canonical five

Revision ID: 20260915_m5canon01
Revises: 20260912_msgctx01
Create Date: 2026-09-15

Rows still hold `m5_writing.final_sections` from the six-chapter era — a
separate "Chương 5 — Thảo luận" and "Chương 6 — Kết luận", and headings a
producer wrote itself ("Chương 4 — Kết quả nghiên cứu") that match no title
map. Every renderer already resolves those to the canonical five, so the
exported document has always been right; the stale shape was only visible to
whoever read the storage directly, which is how the agent came to tell a
student their thesis had seven chapters.

This rewrites the stored list into what the renderer produces: canonical
chapter order, canonical identity (`chapter_name` set explicitly, so nothing
downstream has to guess from a title again), legacy closing chapters merged,
non-chapter sections (References) kept.

NO PROSE IS DROPPED. Every stored section's text is asserted to survive into
the rewritten list before the row is written; a row that would lose any is
left exactly as it is. Idempotent — a canonical row rewrites to itself, so
re-running is a no-op.

Imports the live resolver rather than re-implementing the collapse rule. That
is the usual alembic tradeoff (a later change to the function changes what
this migration would do on a fresh database), accepted here because a second
copy of the merge rule is precisely the failure this whole series is about,
and because the operation is idempotent and loss-guarded. If the import
fails, the migration no-ops rather than half-applying.
"""
from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "20260915_m5canon01"
down_revision = "20260912_msgctx01"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _prose(sec) -> str:
    if not isinstance(sec, dict):
        return ""
    return (sec.get("prose") or sec.get("body") or sec.get("content") or "").strip()


def upgrade() -> None:
    try:
        from orchestrator.tools.m5_writing import sections_from_m5_slice
    except Exception:  # noqa: BLE001 — never block a deploy on a data tidy-up
        logger.warning("m5 final_sections canonicalization skipped: resolver unavailable")
        return

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT project_id, m5_writing FROM context_store WHERE m5_writing IS NOT NULL"
    )).all()

    rewritten = skipped = 0
    for project_id, m5 in rows:
        m5 = m5 or {}
        stored = m5.get("final_sections") or []
        if not stored:
            continue
        try:
            canon = sections_from_m5_slice({"final_sections": stored})
        except Exception:  # noqa: BLE001
            logger.warning("final_sections canonicalization failed for %s", project_id)
            continue
        if not canon:
            continue

        before = [(s.get("chapter_name"), s.get("title")) for s in stored if isinstance(s, dict)]
        if before == [(s.get("chapter_name"), s.get("title")) for s in canon]:
            continue  # already canonical

        # Loss guard: every stored word must still be somewhere in the result.
        blob = "\n".join(_prose(s) for s in canon)
        if any(_prose(s) and _prose(s) not in blob for s in stored):
            logger.warning(
                "final_sections canonicalization SKIPPED for %s — it would drop prose",
                project_id)
            skipped += 1
            continue

        updated = {**m5, "final_sections": canon}
        conn.execute(
            sa.text("UPDATE context_store SET m5_writing = CAST(:v AS jsonb) "
                    "WHERE project_id = :p"),
            {"v": json.dumps(updated, ensure_ascii=False), "p": project_id},
        )
        rewritten += 1

    logger.info("final_sections canonicalized: %d rewritten, %d skipped", rewritten, skipped)


def downgrade() -> None:
    # One-way: the pre-collapse shape is not reconstructable (the two closing
    # chapters are merged into one string, and that merge is the point). The
    # prose is all still there, so nothing needs reversing.
    pass
