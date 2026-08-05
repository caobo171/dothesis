# Tool-run artifacts: keep the input and the output

**Date:** 2026-08-05
**Status:** approved, ready to plan

## The problem

`/transactions → Lượt dùng công cụ` lists what a student ran and what it cost.
It cannot show them *what they got*, because nothing is kept: `tool_runs`
stores counts only ("Sizes and counts, never prose"), and `/document/humanize`
streams the .docx straight back to the browser without persisting it —
deliberately, so a one-shot tool call leaves no litter attached to a project the
student does not have.

The result is a history that can say `-89 credit` and nothing else. A student
who closed the tab has lost the document they paid for, and cannot re-run
without finding the original file again. It also makes support blind: the
translation bug found on 2026-08-05 (an English dissertation rewritten into
Vietnamese) took a manual copy of both files to diagnose, because the run itself
kept nothing.

## What this changes

Both the input and the output .docx of a document tool run are stored on S3 for
**30 days**. The student can re-download either, or re-run the tool from the
stored input without touching their filesystem.

This deliberately crosses the "never prose" line the schema documents today.
That is the point of the feature, and it is why retention, deletion and access
are specified here rather than left to follow.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Retention | 30 days, then purged | Long enough to re-download or notice a problem; bounded storage and bounded exposure. |
| Re-run | Server-side from the stored input, charged normally | A re-run is a real run. One click, no re-upload. |
| Admin access | Owner **or** super admin, journaled | Mirrors `auth_admin.readable_project`. Debugging a bad run is a read. |
| Re-run permission | Owner only | Writes stay owner-only, as with every other route since `40cec09`. |
| Scope | `humanize-docx` and `cite-docx` | The only tools that take a file in and give a file back. |

## Data model

Added to `tool_runs`:

| Column | Type | Notes |
|---|---|---|
| `input_s3_uri` | `Text NULL` | nulled on purge |
| `output_s3_uri` | `Text NULL` | nulled on purge |
| `input_filename` | `String(255) NULL` | so a download gets its real name |
| `files_expire_at` | `timestamptz NULL` | `created_at + 30 days`; the purge job reads this |
| `parent_run_id` | `BigInteger NULL FK tool_runs.id` | re-run lineage |
| `metrics` | `JSONB NULL` | `{"rewritten": 80, "skipped": 52}` — the run's own summary |

The row is **never deleted** on expiry; only the two URIs are nulled. A tool run
is a billing record, and the audit trail must outlive the file it points at.

`metrics` also closes a smaller gap: `humanize_docx` already returns
`rewritten` / `skipped`, and the route throws them away into response headers.
Stored, the history line can say what the run actually did.

## Storage layout

Mirrors the existing uploads convention:

```
s3://<bucket>/users/<user_id>/tool-runs/<uuid4>/input/<filename>
s3://<bucket>/users/<user_id>/tool-runs/<uuid4>/output/<filename>
```

A fresh `uuid4` per run, not the row id — the key is needed before the row is
written.

## Components

### `api/app/tool_artifacts.py` (new)

```
store_run_files(user_id, filename, input_bytes, output_bytes) -> RunFiles
purge_expired(db, s3, now, limit) -> PurgeResult
```

`store_run_files` is **best-effort and never raises**, the same contract
`record_tool_run` holds: an S3 outage must not cost a student the document they
just paid for. On failure it returns empty URIs and the run is recorded without
files.

Called through `run_in_threadpool` — boto3 is synchronous and both document
routes are `async def`.

### `api/app/auth_admin.py`

`readable_run(db, user, run_id) -> ToolRun` — owner or super admin, 404 for
both "does not exist" and "not yours" so the endpoint is not an existence
oracle, and an admin read is journaled. `owned_run(...)` for writes.

### Endpoints (`api/app/routers/tools.py`)

| Route | Method | Auth | Notes |
|---|---|---|---|
| `/tools/runs` | POST | owner | extended with `has_input`, `has_output`, `files_expire_at`, `parent_run_id`, `metrics` |
| `/tools/runs/{id}/file/{which}` | GET | `?st=` scoped `tool-run-file:{id}/{which}` → `readable_run` | 302 to a 5-minute presigned URL. GET because `<a download>` cannot POST — the same exception `uploads`/`exports` already take. |
| `/tools/runs/{id}/rerun` | POST | `owned_run` | loads the input, dispatches on `tool`, charges normally, writes a new row with `parent_run_id` |
| `/tools/runs/{id}/files/delete` | POST | `owned_run` | delete now, without waiting 30 days |

An expired or purged run answers **410** with a message naming the retention
window, not a bare 404 — "it is gone because it aged out" is a different fact
from "no such run".

### `scripts/purge_tool_run_files.py` (new)

Selects rows past `files_expire_at` that still hold a URI, deletes the objects,
nulls the columns, keeps the row. Idempotent, logs counts, safe to re-run.

**A purge script that is never scheduled makes the 30-day promise false.** The
repo has no cron infrastructure today, so wiring this into `deploy/` is part of
this work, not a follow-up.

### Web

`Lượt dùng công cụ` rows expand to `[Tải input] [Tải kết quả] [Chạy lại]`, with
"File được giữ đến <date>" and, when `metrics` is present, `80 đoạn viết lại ·
52 đoạn giữ nguyên`. New i18n keys in both `vi.ts` and `en.ts`.

## Testing

- `store_run_files` with a failing S3 client → run still returns its document.
- Download: stranger 404, owner 302, admin 302 + a journal line.
- Re-run: owner only (admin 404), new row carries `parent_run_id`, charges again.
- Expired run → 410.
- Purge: objects deleted, columns nulled, **row still present**.
- Migration round-trip (up/down) against the real schema.

## Risks

- **Storage growth is unbounded until the purge job actually runs.** Scheduling
  is in scope for exactly this reason.
- **This puts student theses in S3.** Bucket policy and encryption are assumed
  from the existing uploads path, which already stores the same class of
  content; nothing here loosens them.
- Re-run is billable and one click away. The UI must say so before running.
