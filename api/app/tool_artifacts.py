"""Where a document tool run's input and output live, and when they stop living.

Kept out of tool_billing so that module stays about money, but both hold the
same rule and for the same reason: NEVER RAISE. A run reaches this code having
already done its work and charged for it, so a storage failure must degrade to
"no files kept" rather than cost the student the document they just paid for.

Retention is 30 days. That number appears in three places — the expiry written
here, the 410 the download route answers, and the copy the web app shows — and
all three read it from FILE_RETENTION_DAYS so they cannot drift apart. It is
only true if scripts/purge_tool_run_files.py is actually scheduled; an unrun
purge turns the promise in the UI into a false statement.
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .routers.uploads import s3_from_env

logger = logging.getLogger(__name__)

FILE_RETENTION_DAYS = 30

_DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")


@dataclass
class RunFiles:
    """What got stored. All-None means nothing did, which is not an error."""
    input_uri: str | None = None
    output_uri: str | None = None
    expires_at: datetime | None = None


def _bucket() -> str:
    # Project convention is S3_BUCKET; AWS_S3_BUCKET kept as the fallback the
    # exports route already honours.
    return os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET") or ""


def uri_parts(uri: str) -> tuple[str, str]:
    """("bucket", "key") from an s3:// URI. ("", "") when it isn't one."""
    if not (uri or "").startswith("s3://"):
        return "", ""
    _, _, rest = uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    return (bucket, key) if bucket and key else ("", "")


def store_run_files(*, user_id, filename: str, input_bytes: bytes,
                    output_bytes: bytes | None) -> RunFiles:
    """Store both halves of one run under one directory.

    Both halves share a directory so a prefix-based cleanup can never take one
    and leave the other orphaned. The input is stored even when the run FAILED
    and there is no output — that is precisely the case worth being able to
    reproduce, and to re-run without asking the student for the file again.
    """
    try:
        bucket = _bucket()
        if not bucket or not input_bytes:
            return RunFiles()
        safe = (filename or "document.docx").replace("/", "_")[:200]
        run_dir = f"users/{user_id}/tool-runs/{_uuid.uuid4()}"
        s3 = s3_from_env()

        s3.put_object(Bucket=bucket, Key=f"{run_dir}/input/{safe}",
                      Body=input_bytes, ContentType=_DOCX_MIME)
        out_uri = None
        if output_bytes:
            s3.put_object(Bucket=bucket, Key=f"{run_dir}/output/{safe}",
                          Body=output_bytes, ContentType=_DOCX_MIME)
            out_uri = f"s3://{bucket}/{run_dir}/output/{safe}"

        return RunFiles(
            input_uri=f"s3://{bucket}/{run_dir}/input/{safe}",
            output_uri=out_uri,
            expires_at=(datetime.now(timezone.utc)
                        + timedelta(days=FILE_RETENTION_DAYS)),
        )
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("tool artifacts: storing run files failed")
        return RunFiles()


def purge_expired(db: Session, *, s3=None, now: datetime | None = None,
                  limit: int = 500) -> int:
    """Delete the files of runs past their expiry. Returns how many runs.

    Nulls the columns and KEEPS the row: a tool run is a billing record, and
    deleting it to reclaim a file would erase the evidence a student was
    charged. Idempotent — a second pass finds nothing, because the query only
    matches rows that still hold a URI.

    A delete that fails is logged and the row is left alone, so the next run
    retries it rather than orphaning the object silently.
    """
    from .models import ToolRun  # noqa: PLC0415 — avoids a models/app cycle

    now = now or datetime.now(timezone.utc)
    s3 = s3 or s3_from_env()
    rows = db.scalars(
        select(ToolRun)
        .where(ToolRun.files_expire_at.is_not(None), ToolRun.files_expire_at < now)
        .where(or_(ToolRun.input_s3_uri.is_not(None),
                   ToolRun.output_s3_uri.is_not(None)))
        .limit(limit)
    ).all()

    purged = 0
    for row in rows:
        try:
            for uri in (row.input_s3_uri, row.output_s3_uri):
                bucket, key = uri_parts(uri or "")
                if bucket and key:
                    s3.delete_object(Bucket=bucket, Key=key)
            row.input_s3_uri = None
            row.output_s3_uri = None
            purged += 1
        except Exception:  # noqa: BLE001
            logger.exception("tool artifacts: purge failed for run %s", row.id)
    db.commit()
    return purged
