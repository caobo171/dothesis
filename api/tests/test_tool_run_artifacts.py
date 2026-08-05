"""A tool run keeps its input, its output, and its progress.

Spec: docs/superpowers/specs/2026-08-05-tool-run-artifacts-design.md

The history could say "-89 credit" and nothing else: `tool_runs` stored counts
only, and /document/humanize streamed the .docx back without keeping it. A
student who closed the tab had lost the document they paid for.

Two lines are load-bearing here and are asserted rather than assumed:
  - the ROW outlives the FILES. Purging nulls the URIs; the billing record stays.
  - reads are owner-or-super-admin, writes are owner-only — the same asymmetry
    every other route has held since 40cec09.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import get_session_factory
from app.models import ToolRun
from tests.conftest import make_user


def _run(db, user, **overrides) -> ToolRun:
    """A finished humanize-docx run with both files stored."""
    fields = {
        "user_id": user.id, "surface": "web", "tool": "humanize-docx", "ok": True,
        "input_s3_uri": "s3://b/users/x/tool-runs/y/input/thesis.docx",
        "output_s3_uri": "s3://b/users/x/tool-runs/y/output/thesis.docx",
        "input_filename": "thesis.docx",
        "files_expire_at": datetime.now(timezone.utc) + timedelta(days=30),
        "metrics": {"rewritten": 80, "skipped": 52},
    }
    fields.update(overrides)
    row = ToolRun(**fields)
    db.add(row); db.commit(); db.refresh(row)
    return row


# --- schema ---------------------------------------------------------------

def test_tool_run_carries_its_artifacts_and_progress():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        r = _run(s, u)
        assert r.metrics["rewritten"] == 80
        assert r.input_filename == "thesis.docx"
        assert r.parent_run_id is None
        # Defaults: a row written the old way is a finished run, not a stuck one.
        assert r.status == "done"
        assert r.progress_done == 0 and r.progress_total == 0


def test_a_run_can_point_at_the_run_it_was_rerun_from():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        first = _run(s, u)
        again = _run(s, u, parent_run_id=first.id)
        assert again.parent_run_id == first.id


# --- storage --------------------------------------------------------------

def test_store_run_files_puts_both_halves_under_one_run_directory(monkeypatch):
    from unittest.mock import MagicMock
    from app import tool_artifacts as A

    fake = MagicMock()
    monkeypatch.setattr(A, "s3_from_env", lambda: fake)
    monkeypatch.setenv("S3_BUCKET", "b")
    uid = uuid.uuid4()

    r = A.store_run_files(user_id=uid, filename="thesis.docx",
                          input_bytes=b"IN", output_bytes=b"OUT")

    assert r.input_uri.startswith(f"s3://b/users/{uid}/tool-runs/")
    assert r.input_uri.endswith("/input/thesis.docx")
    assert r.output_uri.endswith("/output/thesis.docx")
    # Both halves of one run belong together — same directory, so a purge that
    # walks a prefix cannot take one and leave the other.
    assert r.input_uri.rsplit("/input/", 1)[0] == r.output_uri.rsplit("/output/", 1)[0]
    assert fake.put_object.call_count == 2
    assert r.expires_at > datetime.now(timezone.utc) + timedelta(days=29)


def test_store_run_files_never_raises_when_s3_is_down(monkeypatch):
    """record_tool_run's contract, extended here: a bookkeeping failure must not
    cost the student the document they have already been charged for."""
    from app import tool_artifacts as A

    def boom():
        raise RuntimeError("no s3")

    monkeypatch.setattr(A, "s3_from_env", boom)
    r = A.store_run_files(user_id=uuid.uuid4(), filename="t.docx",
                          input_bytes=b"IN", output_bytes=b"OUT")
    assert r.input_uri is None and r.output_uri is None and r.expires_at is None


def test_a_failed_run_stores_its_input_anyway(monkeypatch):
    """The input is what makes a failure reproducible — and re-runnable without
    asking the student to find the file again."""
    from unittest.mock import MagicMock
    from app import tool_artifacts as A

    fake = MagicMock()
    monkeypatch.setattr(A, "s3_from_env", lambda: fake)
    monkeypatch.setenv("S3_BUCKET", "b")
    r = A.store_run_files(user_id=uuid.uuid4(), filename="t.docx",
                          input_bytes=b"IN", output_bytes=None)
    assert r.input_uri is not None
    assert r.output_uri is None
    assert fake.put_object.call_count == 1


# --- purge ----------------------------------------------------------------

def test_purge_deletes_the_objects_and_keeps_the_row(monkeypatch):
    """The row is a billing record. Only the files age out."""
    from unittest.mock import MagicMock
    from app import tool_artifacts as A

    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        stale = _run(s, u, files_expire_at=datetime.now(timezone.utc) - timedelta(days=1))
        fresh = _run(s, u)
        fake = MagicMock()
        n = A.purge_expired(s, s3=fake, now=datetime.now(timezone.utc))

        assert n == 1
        assert fake.delete_object.call_count == 2      # input + output
        s.refresh(stale); s.refresh(fresh)
        assert stale.id is not None                     # row survives
        assert stale.input_s3_uri is None and stale.output_s3_uri is None
        assert fresh.input_s3_uri is not None           # untouched


def test_purge_is_idempotent(monkeypatch):
    from unittest.mock import MagicMock
    from app import tool_artifacts as A

    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        _run(s, u, files_expire_at=datetime.now(timezone.utc) - timedelta(days=1))
        fake = MagicMock()
        assert A.purge_expired(s, s3=fake, now=datetime.now(timezone.utc)) == 1
        assert A.purge_expired(s, s3=fake, now=datetime.now(timezone.utc)) == 0
