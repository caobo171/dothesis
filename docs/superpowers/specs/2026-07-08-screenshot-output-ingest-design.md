# Screenshot / Image Output Ingest Design (F13)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation (audit CRITICAL):** F8's Output Sanity Layer (`check_thresholds`) assumes the student
**pastes** result tables as text. Real students **screenshot** SmartPLS / AMOS / SPSS output;
retyping a Fornell-Larcker matrix is miserable at peak stress. If the flagship correctness feature
can't be fed from an image (or a SmartPLS HTML/Excel export), it dies at its input — a churn moment.

## Problem

A student finishes their PLS-SEM run, screenshots the bootstrapping/validity tables, and drops the
image into chat expecting interpretation. Today there's no path from that image to structured
`rows` for `check_thresholds`, so the agent either asks them to retype it (friction) or free-hand
interprets the image (ungrounded, error-prone).

## Goals

- **Image → structured table:** parse a screenshot of a results table into
  `{table_kind, rows:[{item/pair, value, …}]}` the F8 layer can classify.
- **Also accept SmartPLS HTML / Excel exports** (deterministic parse — more reliable than vision).
- **Ground the interpretation:** feed parsed rows to `check_thresholds` (F8) so thresholds +
  suspiciously-perfect flags run on real values, and the agent narrates from those, not from a
  vision guess.

## Non-goals

- Not OCR of a whole PDF thesis (that's the import feature) — just results tables.
- Not computing statistics — parsing values the student already has.
- Not a guarantee of perfect parse — low-confidence cells are surfaced for confirmation, never
  silently trusted.

## Design

### Vision parse tool

`parse_output_table(attachment_ref) -> str` in `agent/tools/stats.py` (next to `check_thresholds`):
- Uses the **multimodal model** already wired in the runtime (`agent/multimodal.Attachment`;
  Gemini inline / File API) to read the image into a strict-JSON `{table_kind, rows}`.
- `table_kind` inferred from headers (loadings / htmt / fornell_larcker / vif / path_coeffs /
  fit_indices); low-confidence → returns `needs_confirmation` with the parsed guess.
- The prompt forbids inventing numbers ("transcribe only what is visible; mark unreadable cells").

### Deterministic export parse

`parse_smartpls_export(bytes, filename) -> str` — SmartPLS HTML report / `.xlsx` → the same
`{table_kind, rows}` shape via `pandas`/`openpyxl` + the docx/html table flatten already in
`partner_report_service._extract_text`. Preferred over vision when the student has the file.

### Wire to F8

The M4 skill: on an image/table attachment, call `parse_output_table` (or `parse_smartpls_export`)
→ `check_thresholds(table_kind, rows)` → narrate with the two-register + output-interpretation
content. Low-confidence parses are shown back to the student to confirm before interpreting.

## Data flow

```
student drops a SmartPLS screenshot / HTML export
  → parse_output_table (vision) OR parse_smartpls_export (deterministic)
  → {table_kind, rows} (+ needs_confirmation on low confidence)
  → check_thresholds (F8) → thresholds + suspiciously-perfect flags
  → agent narrates (grounded), asks to confirm any unreadable cells
```

## Error handling

- Vision parse failure / garbled image ⇒ `{"error": "couldn't read the table", "hint": "paste the
  values or upload the SmartPLS HTML export"}` — graceful, offers the deterministic path.
- Never fabricate a value: unreadable cells are `null` + flagged, not guessed.
- `check_thresholds` already tolerates partial rows.

## Testing

- `parse_output_table`: with the vision call stubbed to return a canned JSON ⇒ correct
  `{table_kind, rows}`; a stub returning junk ⇒ `error`/`needs_confirmation`, no crash.
- `parse_smartpls_export`: a small HTML/xlsx fixture with an HTMT table ⇒ rows parsed; feeds
  `check_thresholds` and an HTMT>0.85 row is flagged (end-to-end with F8).
- No real vision API in tests (the model call is stubbed).
- api tests via `./run.sh`.

## Migration / rollout

1. `parse_smartpls_export` (deterministic; most reliable, ships first).
2. `parse_output_table` (vision) with confidence handling.
3. M4 skill wiring → `check_thresholds` → grounded narration + confirm-low-confidence.

## Dependencies

- **F8** (`check_thresholds`, output-interpretation content) — the consumer.
- Runtime multimodal attachment handling (`agent/multimodal.py`) — already present.
- `pandas`/`openpyxl` for the export parse.
