# Recovery doctor — reconcile what a project HAS against what its state SAYS

Date: 2026-09-15
Status: approved for implementation

## The problem

A student's evidence reaches the conversation but never reaches durable state.
The project then looks healthy while being empty, and every later turn starts
blind. There is no mechanism that notices.

Measured on the dev database, 2026-09-15:

- **12 of 21 uploads (57%) were never attached to any message.** All 21
  extracted successfully. The text sits on disk; no turn ever carried it.
- On project `500319a8` both uploads *were* attached, and the results still
  never landed: `m4_analysis.results` is `{}` while
  `uploads/_Result.docx.txt` has held **102 table rows of real coefficients**
  since 06:07 UTC (`| ATT_1 | 0.854 |`, `| DEC_1 | | 0.860 |`, …).

Both present to the student as "tài liệu đã upload lên, chỉ là chưa được đọc".
The second is worse: nothing is missing, nothing errored, and the numbers have
been on disk for hours.

Today the only related machinery is `agent/preflight.py:preflight_check`
(returns a gap list) and `orchestrator/graph_guard.py:repair_conceptual_model`
(one data shape). Nothing reconciles evidence against state.

## Principles fixed by the owner

1. **Auto-repair, then report.** The doctor fixes what it can and tells the
   student in one line. It does not ask first.
2. **Heuristics, not inference.** Diagnosis makes no model call. Where a repair
   genuinely needs a model, it uses the configured default (`gpt-5.6-luna`);
   no new cheap-model route is introduced.
3. **Chapter 4 does not require raw data.** An uploaded SmartPLS/SPSS results
   file is sufficient on its own — extract the results and proceed. Raw data is
   optional.
4. **Paying to re-read context is not an extra charge.** The failure is usually
   "context was not read"; reading it now is the work that should have happened
   the first time.

## Scope

In: detection of the five conditions below, deterministic repair, a directive
for repairs that need the agent, a loop guard, and the `dod_analysis` change
principle 3 requires.

Out: repairing threads retroactively, any UI surface, and re-running vision
over an already-extracted file (that cost was paid at upload).

## Architecture

Layering rule (`agent/` must never import `app/`) forces a split:

- **`orchestrator/doctor.py`** — pure diagnosis. Takes a `DoctorInput`
  assembled by the caller; returns `list[Finding]`. No DB, no filesystem, no
  network, no model. Every check is a function of its arguments, so the whole
  suite is unit-testable with literals.
- **`api/app/doctor_adapter.py`** — gathers `DoctorInput` from Postgres and the
  workspace mirror, applies the deterministic repairs through
  `DbProjectStateStore`, and renders the directive string. This is the only
  half that touches I/O.

`chat_v3.send_message_v3` calls the adapter once per turn, where
`_new_context_backfill_directive` is called today. That function is subsumed by
the doctor and deleted; its backfill check becomes `BACKFILL_AVAILABLE` below
and its tests move with it.

### Types

```python
@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    sidecar_text: str | None   # uploads/<name>.txt if present, else None
    ever_attached: bool

@dataclass(frozen=True)
class DoctorInput:
    # PER-MODULE slices, exactly as load_full_context_store() returns them:
    # {"m1_topic": {...}, "m4_analysis": {...}}. Not flattened — every slice
    # carries its own `confirmed_at`, so a flat dict cannot say WHICH module
    # is falsely marked done, and `reconstructable_modules` wants this shape
    # anyway.
    context_store: dict
    uploads: list[UploadRecord]
    chapter_prose: dict[str, str]  # from m5_writing.chapter_prose

@dataclass(frozen=True)
class Finding:
    code: str                    # one of the five below
    detail: str                  # student-facing, one line, Vietnamese or English
    repair: str                  # "deterministic" | "directive" | "ask_student"
    payload: dict                # what the repair needs (e.g. parsed rows)
```

## The five checks

All are pure functions over `DoctorInput`.

| Code | Detection | Repair |
|---|---|---|
| `UNREAD_UPLOAD` | `sidecar_text` present and `ever_attached` false | deterministic — attach to the next turn |
| `RESULTS_NOT_IN_STATE` | a sidecar holds ≥1 parseable coefficient table AND `m4_analysis.results` is empty | deterministic — parse and commit |
| `FALSE_DONE` | `confirmed_at` set on a slice whose `dod_*()` returns `done=False` | deterministic — clear the flag |
| `REFUSAL_CHAPTER` | `_is_stub_prose(prose)` true for a chapter in `chapter_prose` | directive — recompose, and tell the student |
| `BACKFILL_AVAILABLE` | `reconstructable_modules()` non-empty | directive — call `backfill_upstream_modules` |

`RESULTS_NOT_IN_STATE` is the highest-value check and the cheapest: SQL plus a
regex, repaired by a text parse.

### The results parser

The fiddly part, and the one most likely to be wrong. `_Result.docx.txt` holds
102 coefficient rows spread across several tables (outer loadings, CR/AVE,
HTMT, VIF, R²), distinguished only by the heading above each block.

Rules:
- Split the sidecar on markdown/plain headings; each block becomes one table.
- A block qualifies only if it has a pipe row matching `[0-9]\.[0-9]{2,}`.
- Map the heading to a canonical table name by keyword
  (`Cronbach`/`CR`/`AVE` → `reliability`, `HTMT` → `discriminant_validity`,
  `VIF` → `collinearity`, `R²`/`R2` → `explained_variance`, outer loading
  patterns → `outer_loadings`). An unrecognised heading keeps its own text as
  the key rather than being dropped.
- Emit ONE dict keyed by table — the shape `analysis_results` requires. The
  list shape silently shipped a Chapter 4 with no tables once already.
- Parse nothing and commit nothing when no block qualifies. A partial parse is
  worse than none, because it reads as a finished analysis.

Persistence is verified: `results` IS in `SLICE_OWNERSHIP["M4"]`, so
`commit_slice("M4", {"results": …})` round-trips. (The comment in
`dod_analysis` claiming `results` is "not M4-owned" is stale and gets corrected
in the same change.)

## `dod_analysis` must stop requiring raw data

Principle 3. Today `dod_analysis` reports `results is empty` for a project whose
results file is sitting parsed on disk, because the numbers never moved. Once
`RESULTS_NOT_IN_STATE` commits them, `results` is populated and the existing
gate passes unchanged — no threshold change is needed for the common case.

The change needed is narrower: the stale ownership comment, and a test pinning
that an M4 whose numbers came from an uploaded results export (not from
`run_stats` on raw data) reads `done=True`. Raw data must never be a
precondition.

## Loop guard

A repair that runs, changes nothing, and runs again next turn bills forever.

After each repair the adapter records `{code, gaps_before, gaps_after}` per
module. If `gaps_after == gaps_before`, that `code` is marked exhausted and is
not retried. Exhaustion resets when new evidence arrives — a new upload row, or
any change to the module's slice. That reset condition is the same "new
context" signal the backfill directive already keys on.

Exhausted findings are not silent: they convert to `ask_student`, which is how
"chưa thể viết Chương 3 vì thiếu X" reaches the student as a message rather
than as prose inside the chapter.

## Persistence

The repair log needs a home. `context_store` has a free-standing `coaching`
JSONB column; the log goes in a sibling `doctor` column added by an Alembic
migration, NOT inside a module slice — slices are the student's work and a
diagnostic ledger does not belong in one.

**`DbProjectStateStore` only round-trips `SLICE_OWNERSHIP` keys.** A new column
therefore needs explicit `load`/`_save` support plus a round-trip test, or it
is dead in production. This has already happened once in this codebase; the
round-trip test is not optional.

## Testing

- `orchestrator/tests/test_doctor.py` — each check against literals, both
  directions. No DB, no model.
- `orchestrator/tests/test_doctor_results_parser.py` — the parser against the
  **real `_Result.docx.txt`**, committed as a fixture. Asserts a dict keyed by
  table, `outer_loadings` containing `ATT_1 → 0.854`, and that a sidecar with
  no coefficient table yields `{}`.
- `api/tests/test_doctor_adapter.py` — round-trip through
  `DbProjectStateStore`, including the `doctor` column, and the loop guard
  (same gaps twice → exhausted → not retried → surfaces as `ask_student`).
- The existing `api/tests/test_chat_v3_new_context_backfill.py` moves onto the
  doctor's `BACKFILL_AVAILABLE` finding.

## Risks

- **Mis-keyed tables.** Heading→table mapping is heuristic; a mis-keyed table
  puts HTMT numbers under reliability. Mitigated by keying unknown headings to
  their own text instead of guessing, and by the real-file fixture.
- **Doctor runs on every turn.** All five checks are pure and cheap, but they
  read the full context store. Acceptable: the adapter already loads it for the
  state header.
- **Auto-repair acting against intent.** Deterministic repairs only move
  evidence the student supplied into the state that describes it; none of them
  writes prose or invents a number.
