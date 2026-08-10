"""Shared machinery for the partner .docx tools.

Three of them now — humanize, similarity, citation — and each needs the same
four things: presign an artifact, close a run that crashed, decide when a run
that stopped reporting is lost, and project a ToolRun row into the status shape
partners poll. The second copy of that was tolerable; a third is how the
staleness window ends up different in one tool and nobody notices for a month.

What deliberately does NOT live here is the work itself or its metrics. Those
differ per tool and pretending otherwise would produce a parameterised
super-function that is harder to read than the three call sites it replaced.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ToolRun
from ..tool_artifacts import uri_parts

logger = logging.getLogger(__name__)

# How long a row may sit in `running` before status calls it lost. A process
# restart mid-run leaves the row open forever otherwise, and a caller polling a
# dead run learns nothing by polling it for another day.
STALE_AFTER = timedelta(minutes=90)

# Live worker threads, so tests can wait for one deterministically instead of
# sleeping. Production never reads this.
_WORKERS: list[threading.Thread] = []


def join_workers(timeout: float = 60) -> None:
    """TEST HELPER — block until every started run has finished."""
    for thread in list(_WORKERS):
        thread.join(timeout)


def start_worker(target, *args) -> None:
    """Run `target(*args)` on a daemon thread, tracked for join_workers."""
    thread = threading.Thread(target=target, args=args, daemon=True)
    _WORKERS.append(thread)
    thread.start()


def presign(uri: str | None, expires: int = 3600) -> str | None:
    """Short-lived GET url for an s3:// artifact uri. None on anything odd."""
    bucket, key = uri_parts(uri or "")
    if not bucket or not key:
        return None
    try:
        from .uploads import s3_from_env  # noqa: PLC0415

        return s3_from_env().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)
    except Exception:  # noqa: BLE001
        logger.exception("partner docx: presign failed for %s", uri)
        return None


def fail_run(run_id: int, code: str) -> None:
    """Close a run as failed from a worker. Own session; never raises."""
    from ..db import get_session_factory  # noqa: PLC0415

    try:
        session_factory = get_session_factory()
        with session_factory() as s:
            row = s.get(ToolRun, run_id)
            if row is None:
                return
            row.status, row.ok, row.error = "failed", False, code
            s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("partner docx: could not mark run %s failed", run_id)


def find_partner_run(db: Session, run_id: int, owner_id, tool: str) -> ToolRun | None:
    """The row, but only if it is genuinely this partner's.

    Scoped to the partner system user AND surface="partner" AND the tool: ids
    are sequential and partner auth is one shared secret, so without that scope
    a guessed id would read a real student's run.
    """
    return db.scalar(
        select(ToolRun).where(ToolRun.id == run_id,
                              ToolRun.user_id == owner_id,
                              ToolRun.surface == "partner",
                              ToolRun.tool == tool))


def status_payload(row: ToolRun) -> dict:
    """Project a run row into the shape every partner tool polls.

    `metrics` carries whatever that tool recorded, so the per-tool differences
    ride inside one envelope instead of forking the contract.
    """
    common = {
        "done": row.progress_done,
        "total": row.progress_total,
        "filename": row.input_filename,
        "credits_charged": row.credits_charged,
        "metrics": row.metrics,
    }
    if row.status == "running":
        created = row.created_at
        if created and datetime.now(timezone.utc) - created > STALE_AFTER:
            return {**common, "status": "error", "ok": False,
                    "error": "run_lost", "docx_url": None}
        return {**common, "status": "processing", "ok": False,
                "error": None, "docx_url": None}
    if not row.ok:
        return {**common, "status": "error", "ok": False,
                "error": row.error or "failed", "docx_url": None}
    return {**common, "status": "done", "ok": True, "error": None,
            "docx_url": presign(row.output_s3_uri)}
