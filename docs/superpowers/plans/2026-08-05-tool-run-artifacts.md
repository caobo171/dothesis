# Tool-Run Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the input and output .docx of a document tool run on S3 for 30 days, so a student can re-download either or re-run the tool without their original file.

**Architecture:** Six new nullable columns on `tool_runs`; a new best-effort `tool_artifacts` module that puts both files under `users/<uid>/tool-runs/<uuid4>/`; a scoped-stream-token download route and an owner-only re-run route on the existing tools router; a purge script that nulls the URIs and keeps the row.

**Tech Stack:** FastAPI, SQLAlchemy 2 typed `Mapped[]`, Alembic, boto3, Next.js 16 client components, pytest.

## Global Constraints

- **POST-only** for new endpoints (`CLAUDE.md`). The single exception is the file download, which is a browser `<a download>` GET authenticated by a `?st=` stream token — the same exception `uploads.download_upload` and `exports.download_export` already take.
- **Migration head is `20260805_toolruns01`.** New migration sets `down_revision = "20260805_toolruns01"`.
- **Reads are owner-or-super-admin and journaled; writes are owner-only.** Established by `40cec09`, implemented in `api/app/auth_admin.py`.
- **404, never 403,** for a run the caller may not see — the route must not become an existence oracle.
- **Never raise from artifact storage or billing.** `record_tool_run` documents the rule: work that already succeeded must not be lost to a bookkeeping failure.
- Retention: **30 days**. `files_expire_at = created_at + timedelta(days=30)`.
- API tests need Docker (testcontainer Postgres). `orchestrator`-level tests do not.
- Run everything through `api/run.sh` (arm64 wrapper), never `.venv/bin` directly.

---

### Task 1: Schema — columns + model

**Files:**
- Create: `api/migrations/versions/20260805_tool_run_artifacts.py`
- Modify: `api/app/models.py:599-623` (`ToolRun`)
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Produces: `ToolRun.input_s3_uri`, `.output_s3_uri`, `.input_filename`, `.files_expire_at`, `.parent_run_id`, `.metrics` — all nullable.

- [ ] **Step 1: Write the failing test**

```python
def test_tool_run_carries_artifact_columns():
    from app.db import get_session_factory
    from app.models import ToolRun
    from tests.conftest import make_user
    from datetime import datetime, timedelta, timezone

    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        exp = datetime.now(timezone.utc) + timedelta(days=30)
        r = ToolRun(user_id=u.id, surface="web", tool="humanize-docx", ok=True,
                    input_s3_uri="s3://b/users/x/tool-runs/y/input/a.docx",
                    output_s3_uri="s3://b/users/x/tool-runs/y/output/a.docx",
                    input_filename="a.docx", files_expire_at=exp,
                    metrics={"rewritten": 80, "skipped": 52})
        s.add(r); s.commit(); s.refresh(r)
        assert r.metrics["rewritten"] == 80
        assert r.parent_run_id is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd api && ./run.sh pytest tests/test_tool_run_artifacts.py -q`
Expected: FAIL — `TypeError: 'input_s3_uri' is an invalid keyword argument for ToolRun`.

- [ ] **Step 3: Add the columns to the model**

```python
    # --- artifacts (nullable: a run may predate this, or its files may have
    # aged out). The ROW outlives the files: on purge these go NULL and the
    # billing record stays.
    input_s3_uri: Mapped[str | None] = mapped_column(Text)
    output_s3_uri: Mapped[str | None] = mapped_column(Text)
    input_filename: Mapped[str | None] = mapped_column(String(255))
    files_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True)
    parent_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tool_runs.id", ondelete="SET NULL"))
    # {"rewritten": int, "skipped": int} — counts, never prose.
    metrics: Mapped[dict | None] = mapped_column(JSONB)
```

Add `JSONB` to the `sqlalchemy.dialects.postgresql` import if absent.

- [ ] **Step 4: Write the migration**

```python
"""tool_runs — keep the input/output .docx for 30 days.

Revision ID: 20260805_toolartifact01
Revises: 20260805_toolruns01
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260805_toolartifact01"
down_revision = "20260805_toolruns01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_runs", sa.Column("input_s3_uri", sa.Text(), nullable=True))
    op.add_column("tool_runs", sa.Column("output_s3_uri", sa.Text(), nullable=True))
    op.add_column("tool_runs", sa.Column("input_filename", sa.String(255), nullable=True))
    op.add_column("tool_runs", sa.Column("files_expire_at",
                                          sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_runs", sa.Column("parent_run_id", sa.BigInteger(), nullable=True))
    op.add_column("tool_runs", sa.Column("metrics", postgresql.JSONB(), nullable=True))
    op.create_foreign_key("fk_tool_runs_parent", "tool_runs", "tool_runs",
                          ["parent_run_id"], ["id"], ondelete="SET NULL")
    # The purge job's only query: rows past expiry that still hold a file.
    op.create_index("ix_tool_runs_files_expire_at", "tool_runs", ["files_expire_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_files_expire_at", table_name="tool_runs")
    op.drop_constraint("fk_tool_runs_parent", "tool_runs", type_="foreignkey")
    for col in ("metrics", "parent_run_id", "files_expire_at",
                "input_filename", "output_s3_uri", "input_s3_uri"):
        op.drop_column("tool_runs", col)
```

- [ ] **Step 5: Run the test — it passes**

Run: `cd api && ./run.sh pytest tests/test_tool_run_artifacts.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/models.py api/migrations/versions/20260805_tool_run_artifacts.py api/tests/test_tool_run_artifacts.py
git commit -m "feat(tools): tool_runs carries its input/output artifacts"
```

---

### Task 2: `tool_artifacts.store_run_files`

**Files:**
- Create: `api/app/tool_artifacts.py`
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Consumes: `app.routers.uploads.s3_from_env`.
- Produces:
  ```python
  @dataclass
  class RunFiles:
      input_uri: str | None = None
      output_uri: str | None = None
      expires_at: datetime | None = None

  FILE_RETENTION_DAYS = 30
  def store_run_files(*, user_id, filename: str, input_bytes: bytes,
                      output_bytes: bytes | None) -> RunFiles
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_store_run_files_puts_both_under_the_user_prefix(monkeypatch):
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
    # Same run directory for both halves.
    assert r.input_uri.rsplit("/input/", 1)[0] == r.output_uri.rsplit("/output/", 1)[0]
    assert fake.put_object.call_count == 2
    assert r.expires_at is not None


def test_store_run_files_never_raises_when_s3_is_down(monkeypatch):
    """The contract record_tool_run holds: a bookkeeping failure must not cost
    the student the document they already paid for."""
    from app import tool_artifacts as A
    def boom():
        raise RuntimeError("no s3")
    monkeypatch.setattr(A, "s3_from_env", boom)
    r = A.store_run_files(user_id=uuid.uuid4(), filename="t.docx",
                          input_bytes=b"IN", output_bytes=b"OUT")
    assert r.input_uri is None and r.output_uri is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && ./run.sh pytest tests/test_tool_run_artifacts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tool_artifacts'`.

- [ ] **Step 3: Implement**

```python
"""Where a document tool run's input and output live for 30 days.

Kept OUT of tool_billing so that module stays about money. Both modules share
one rule: never raise. A failed put must not lose a document the student has
already been charged for, so a storage outage degrades to "no files kept" and
the run is recorded without them.
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .routers.uploads import s3_from_env

logger = logging.getLogger(__name__)

FILE_RETENTION_DAYS = 30


@dataclass
class RunFiles:
    input_uri: str | None = None
    output_uri: str | None = None
    expires_at: datetime | None = None


def _bucket() -> str:
    return os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET") or ""


def store_run_files(*, user_id, filename: str, input_bytes: bytes,
                    output_bytes: bytes | None) -> RunFiles:
    """Store both halves of a run under one directory. Best-effort."""
    try:
        bucket = _bucket()
        if not bucket or not input_bytes:
            return RunFiles()
        safe = (filename or "document.docx").replace("/", "_")[:200]
        run_dir = f"users/{user_id}/tool-runs/{_uuid.uuid4()}"
        s3 = s3_from_env()
        mime = ("application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document")
        s3.put_object(Bucket=bucket, Key=f"{run_dir}/input/{safe}",
                      Body=input_bytes, ContentType=mime)
        out_uri = None
        if output_bytes:
            s3.put_object(Bucket=bucket, Key=f"{run_dir}/output/{safe}",
                          Body=output_bytes, ContentType=mime)
            out_uri = f"s3://{bucket}/{run_dir}/output/{safe}"
        return RunFiles(
            input_uri=f"s3://{bucket}/{run_dir}/input/{safe}",
            output_uri=out_uri,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=FILE_RETENTION_DAYS),
        )
    except Exception:  # noqa: BLE001 — see module docstring
        logger.exception("tool artifacts: storing run files failed")
        return RunFiles()
```

- [ ] **Step 4: Run — both pass.** `cd api && ./run.sh pytest tests/test_tool_run_artifacts.py -q`

- [ ] **Step 5: Commit**

```bash
git add api/app/tool_artifacts.py api/tests/test_tool_run_artifacts.py
git commit -m "feat(tools): best-effort S3 storage for tool-run files"
```

---

### Task 3: Record the files on the run

**Files:**
- Modify: `api/app/tool_billing.py:108-150` (`record_tool_run`), `:210-227` (`_write_run`)
- Modify: `api/app/routers/tools.py` — `humanize_document`, `cite_document`
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Consumes: `RunFiles` from Task 2.
- Produces: `record_tool_run(..., files: RunFiles | None = None, metrics: dict | None = None, parent_run_id: int | None = None)`; `ToolCharge.run_id: int | None` so a route can link a re-run.

- [ ] **Step 1: Write the failing test**

```python
def test_the_run_row_points_at_the_stored_files(monkeypatch):
    from app.tool_artifacts import RunFiles
    from app.tool_billing import record_tool_run
    from app.models import ToolRun
    from app.db import get_session_factory
    from tests.conftest import make_user
    from datetime import datetime, timezone

    Session = get_session_factory()
    with Session() as s:
        u = make_user(s); s.commit()
        files = RunFiles(input_uri="s3://b/in.docx", output_uri="s3://b/out.docx",
                         expires_at=datetime.now(timezone.utc))
        res = record_tool_run(s, u, tool="humanize-docx", ok=True, files=files,
                              metrics={"rewritten": 3, "skipped": 1})
        row = s.get(ToolRun, res.run_id)
        assert row.input_s3_uri == "s3://b/in.docx"
        assert row.metrics == {"rewritten": 3, "skipped": 1}
```

- [ ] **Step 2: Run it, watch it fail** — `TypeError: record_tool_run() got an unexpected keyword argument 'files'`.

- [ ] **Step 3: Thread the arguments through**

In `ToolCharge` add `run_id: int | None = None`. In `record_tool_run` accept
`files`, `metrics`, `parent_run_id` and pass them to `_write_run`; in
`_write_run` set the columns and, after `db.commit()`, `result.run_id = row.id`.

- [ ] **Step 4: Store the files from both document routes**

In `humanize_document`, after the threadpool call:

```python
    files = await run_in_threadpool(
        store_run_files, user_id=user.id, filename=file.filename or "document.docx",
        input_bytes=body, output_bytes=out)
    charged = record_tool_run(
        db, user, surface=surface_of(request), tool="humanize-docx", ok=ok,
        error=None if ok else (report.get("error") or "rewrite_failed"),
        usage=report.get("usage") or [], duration_ms=t.ms, files=files,
        # Counts the header already carried and the history threw away, so a
        # run that skipped half the document says so afterwards.
        metrics={"rewritten": report.get("rewritten", 0),
                 "skipped": report.get("skipped", 0)}).charged
```

Same shape in `cite_document` with `metrics={"resolved": …, "unresolved": …, "added": …}`.

- [ ] **Step 5: Run the API tool tests** — `cd api && ./run.sh pytest tests/test_tool_run_artifacts.py tests/test_tools_router.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/tool_billing.py api/app/routers/tools.py api/tests/test_tool_run_artifacts.py
git commit -m "feat(tools): document runs record their files and their counts"
```

---

### Task 4: `readable_run` / `owned_run`

**Files:**
- Modify: `api/app/auth_admin.py`
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Produces: `readable_run(db, user, run_id) -> ToolRun`, `owned_run(db, user, run_id) -> ToolRun`.

- [ ] **Step 1: Write the failing tests** — owner gets the row; a stranger gets 404; a super admin (`caotest171@gmail.com`, on `admin_config._SEED`) gets the row from `readable_run` and 404 from `owned_run`.

```python
def test_readable_run_admits_owner_and_admin_but_not_a_stranger():
    from fastapi import HTTPException
    from app.auth_admin import readable_run, owned_run
    # ... build a run owned by `student`, then:
    assert readable_run(db, student, run.id).id == run.id
    assert readable_run(db, admin, run.id).id == run.id
    with pytest.raises(HTTPException) as e:
        readable_run(db, stranger, run.id)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        owned_run(db, admin, run.id)      # writes stay owner-only
```

- [ ] **Step 2: Run, watch it fail** — `ImportError: cannot import name 'readable_run'`.

- [ ] **Step 3: Implement**, mirroring `readable_project` exactly — same 404-not-403 reasoning, same `log.info("admin_read tool_run=%s owner_id=%s admin=%s", ...)` journal line.

- [ ] **Step 4: Run — PASS.**

- [ ] **Step 5: Commit** `git commit -m "feat(tools): owner-or-admin read gate for a tool run"`

---

### Task 5: Download route

**Files:**
- Modify: `api/app/routers/tools.py`
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Produces: `GET /tools/runs/{run_id}/file/{which}`, scope `tool-run-file:{run_id}/{which}`.

- [ ] **Step 1: Write the failing tests** — owner 302; stranger 404; admin 302; a run whose `files_expire_at` has passed (or whose URI is NULL) 410.

- [ ] **Step 2: Run, watch them fail** (404 — no such route).

- [ ] **Step 3: Implement**

```python
@router.get("/runs/{run_id}/file/{which}")
def download_run_file(
    run_id: int, which: str,
    # GET-only (browser <a download>) — the ?st= token is scoped to this exact
    # run AND half, so a leaked URL opens one file for two minutes.
    user: User = Depends(stream_user_factory(
        lambda run_id, which: f"tool-run-file:{run_id}/{which}")),
    db: Session = Depends(db_session),
):
    from ..auth_admin import readable_run  # noqa: PLC0415
    if which not in ("input", "output"):
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    run = readable_run(db, user, run_id)
    uri = run.input_s3_uri if which == "input" else run.output_s3_uri
    if not uri:
        # 410, not 404: "it aged out" is a different fact from "no such run",
        # and the student is entitled to the difference.
        raise HTTPException(410, detail={"error": {
            "code": "file_expired",
            "message": f"Files are kept for {FILE_RETENTION_DAYS} days."}})
    ...  # presign exactly as uploads.download_upload does, 300s
```

- [ ] **Step 4: Run — PASS.**  - [ ] **Step 5: Commit.**

---

### Task 6: Re-run route

**Files:**
- Modify: `api/app/routers/tools.py`
- Test: `api/tests/test_tool_run_artifacts.py`

**Interfaces:**
- Produces: `POST /tools/runs/{run_id}/rerun`, body `RerunBody(AuthedBody)`.

- [ ] **Step 1: Write the failing tests** — owner re-runs and gets a new row whose `parent_run_id` is the original and which charges again; admin gets 404; a run with no stored input gets 410; a tool that is not a document tool gets 422.

- [ ] **Step 2: Run, watch them fail.**

- [ ] **Step 3: Implement** — `owned_run`, fetch the input from S3 (`get_object`), dispatch on `run.tool` (`humanize-docx` → `humanize_docx`, `cite-docx` → `cite_docx`) through `run_in_threadpool`, store new files, `record_tool_run(..., parent_run_id=run.id)`, stream the .docx back with the same headers the original route sends.

- [ ] **Step 4: Run — PASS.**  - [ ] **Step 5: Commit.**

---

### Task 7: Purge

**Files:**
- Create: `scripts/purge_tool_run_files.py`
- Modify: `deploy/` cron definition
- Test: `api/tests/test_tool_run_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_purge_deletes_the_objects_and_keeps_the_row(monkeypatch):
    """The row is a billing record. Only the files age out."""
    # run with files_expire_at in the past
    deleted = purge_expired(db, s3=fake, now=datetime.now(timezone.utc))
    assert deleted == 1
    assert fake.delete_object.call_count == 2
    row = db.get(ToolRun, run_id)
    assert row is not None                    # row survives
    assert row.input_s3_uri is None and row.output_s3_uri is None
```

- [ ] **Step 2: Run, watch it fail.**

- [ ] **Step 3: Implement `purge_expired` in `tool_artifacts.py`** — select rows where `files_expire_at < now` and either URI is non-null, `delete_object` each, null the columns, commit in batches, return the count. Idempotent.

- [ ] **Step 4: Write the script** — argparse `--limit`, `--dry-run`; logs `purged N runs`.

- [ ] **Step 5: Schedule it.** Add the cron entry to `deploy/`. **Unscheduled, the 30-day retention in the UI copy is a false statement** — this step is not optional.

- [ ] **Step 6: Run — PASS.**  - [ ] **Step 7: Commit.**

---

### Task 8: Web UI

**Files:**
- Modify: `web/app/(inapp)/tools/_components/use-tool.ts`, the transactions page rendering `Lượt dùng công cụ`, `web/app/lib/i18n/messages/{en,vi}.ts`
- Modify: `api/app/routers/tools.py` — `MyRun` gains `has_input`, `has_output`, `files_expire_at`, `parent_run_id`, `metrics`

- [ ] **Step 1: Extend `MyRun` and the `/tools/runs` projection** (booleans, not URIs — the client never needs the S3 key).
- [ ] **Step 2: Add `runFileUrl(runId, which)`** to `use-tool.ts`, minting `tool-run-file:{id}/{which}` via `mintStreamToken` exactly as `triggerUploadDownload` does.
- [ ] **Step 3: Add `rerunToolRun(runId)`** with the same `docTimeoutMs` deadline and `docRequestError` mapping the document routes use.
- [ ] **Step 4: Render** the expanded row: `[Tải input] [Tải kết quả] [Chạy lại]`, "File được giữ đến <date>", and the metrics line. The re-run button must say it costs credits **before** it runs.
- [ ] **Step 5: i18n keys in both locales.**
- [ ] **Step 6: `npx tsc --noEmit`** — clean on non-test files.
- [ ] **Step 7: Commit.**

---

## Self-review

- **Spec coverage:** data model → T1; storage → T2; recording + metrics → T3; access gate → T4; download → T5; re-run → T6; retention + scheduling → T7; UI → T8. All spec sections are covered.
- **Type consistency:** `RunFiles` (T2) is the type passed as `files=` (T3); `ToolCharge.run_id` (T3) is what T6 reads to set `parent_run_id`; `FILE_RETENTION_DAYS` (T2) is the constant the 410 message (T5) and the UI copy (T8) both quote.
- **Known gap:** Tasks 1 and 3–8 need Docker for the API test suite. `store_run_files` (T2) is the only one testable without it.
