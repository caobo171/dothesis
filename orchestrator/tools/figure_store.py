"""Durable storage for the screenshots Chapter 4 embeds.

The student's own SmartPLS screenshots are what a supervisor recognises as
software output; a table of retyped numbers is not. So the extraction pass saves
each transcribed figure and `results_render._figure_body` embeds the original.

Those files used to live ONLY on the local disk. The document they came out of
went to S3, its extracted text went to S3, and the figures — the one part the
exported thesis actually renders — were written to `var/jobs/…/uploads/<name>.img/`
inside a `except Exception: pass`, then recorded in Postgres as an ABSOLUTE path
(`/Users/someone/project/dothesis/var/jobs/…`). Two consequences, both silent:

  - the path is meaningless on any other machine, so the row does not survive a
    restore, a second worker, or the dev/prod split;
  - `var/jobs` is not durable. A redeploy or a disk sweep takes the figures, and
    the only symptom is Chapter 4 quietly falling back to a rebuilt markdown
    table — no error, no warning, just weaker evidence in the document.

This module puts them where the rest of the upload already goes. Keys mirror the
workspace-relative path under one project prefix, so a figure can be found from
nothing but the project id and the relpath the sidecar already records.

Fail-open everywhere: without S3 configured (dev, tests) every function returns
None and the callers keep using the local mirror exactly as before.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEME = "s3://"


def _bucket() -> str | None:
    # S3_BUCKET is the project convention (settings.py, job_runner, uploads and
    # the engine all read it); AWS_S3_BUCKET stays as a back-compat fallback.
    return os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET") or None


def _client():
    import boto3  # noqa: PLC0415 — optional at import time; absent in unit tests

    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


def figure_key(project_id: str, relpath: str) -> str:
    """S3 key for a workspace-relative figure path.

    Mirrors the relpath so the key is derivable from what the sidecar already
    writes ("uploads/_Result.docx.img/hinh-09.png") plus the project id —
    nothing extra has to be stored to find the object again.
    """
    clean = str(relpath or "").replace("\\", "/").lstrip("/")
    return f"projects/{project_id}/figures/{clean}"


def figure_uri(project_id: str, relpath: str) -> str | None:
    bucket = _bucket()
    return f"{_SCHEME}{bucket}/{figure_key(project_id, relpath)}" if bucket else None


def put_figure(project_id: str, relpath: str, body: bytes,
               content_type: str = "image/png") -> str | None:
    """Store one figure. Returns its `s3://` URI, or None when S3 is unavailable."""
    bucket = _bucket()
    if not (bucket and body and relpath):
        return None
    try:
        _client().put_object(Bucket=bucket, Key=figure_key(project_id, relpath),
                             Body=body, ContentType=content_type or "image/png")
    except Exception:  # noqa: BLE001 — an upload must not fail on the mirror
        logger.warning("figure upload failed for %s", relpath, exc_info=True)
        return None
    return figure_uri(project_id, relpath)


def exists(project_id: str, relpath: str) -> bool:
    bucket = _bucket()
    if not bucket:
        return False
    try:
        _client().head_object(Bucket=bucket, Key=figure_key(project_id, relpath))
        return True
    except Exception:  # noqa: BLE001 — "not there" and "cannot ask" are the same here
        return False


def _cache_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "dothesis_figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def localize(value: str) -> str | None:
    """A path the exporter can open, for either stored form.

    Pandoc and Pillow both need a real file, so an `s3://` value is fetched to a
    content-addressed cache first. A plain path is returned when it still exists
    — which keeps every row written before this module behaving exactly as it
    did, and keeps dev off the network.
    """
    value = str(value or "")
    if not value:
        return None
    if not value.startswith(_SCHEME):
        return value if os.path.isfile(value) else None

    bucket, _, key = value[len(_SCHEME):].partition("/")
    if not (bucket and key):
        return None
    # Keyed by the URI, not the filename: two projects both have hinh-09.png.
    cached = _cache_dir() / (hashlib.sha256(value.encode()).hexdigest()[:16]
                             + Path(key).suffix)
    if cached.is_file() and cached.stat().st_size > 0:
        return str(cached)
    try:
        body = _client().get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception:  # noqa: BLE001 — a missing figure degrades to the table
        logger.debug("figure fetch failed for %s", value, exc_info=True)
        return None
    if not body:
        return None
    cached.write_bytes(body)
    return str(cached)
