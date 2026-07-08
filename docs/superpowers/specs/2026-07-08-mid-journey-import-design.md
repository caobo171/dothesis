# Mid-Journey State Import Design (F12)

**Date:** 2026-07-08
**Status:** Design — approved, revised after Fable-5 re-audit (now an API-layer route).
**Motivation (audit CRITICAL):** Most paying students arrive **mid-thesis** — topic approved, data
collected, or three chapters written. DoThesis state is *earned*, so today's agent would insist on
M1. This is the biggest tagline gap ("goes with your journey" must mean *joining* a journey in
progress) AND the missing first-run activation moment. The `partner_report_service` inference does
~70% of the work.

## Problem

A student uploads their proposal + two chapters + an SPSS output and expects the agent to "catch
up." Instead the roadmap shows everything `locked` at M1 — the make-or-break first session feels
like the tool ignored their work.

## Goals

- **Import from uploads:** classify existing material and **infer per-module slices**, committing
  them as *earned* state so the roadmap starts where the student actually is.
- **Earned, evidenced server-side:** extraction/inference run in the **API layer** from the actual
  uploaded files (not model-supplied text), then commit via `commit_slice`.
- **Activation:** the first session opens at the right module with a "here's where you are / next
  do X" summary.

## Non-goals

- Not plagiarism/authorship checking; not grading imported quality (F3 later).
- Doesn't fabricate modules — only what an upload evidences.

## Design (revised: API-layer, not an agent tool)

**Why API-layer:** the inference helpers live in `app.partner_report_service`, and **`agent/` must
not import `app/`** (verified: no such import exists today). Running import in the API layer also
means extraction is **server-side from real files**, closing the model-supplied-evidence hole.

### Classify + infer — `api/app/import_work.py`

`import_existing_work(files: list[dict], language: str) -> dict` → `{slices: {M1..M5: {...}},
evidence: {module: filename}, ambiguous: [...], unreadable: [...]}`. `files = [{filename, text}]`
already extracted + neutralized by the route. Classification: extension + a cheap
`orchestrator`-LLM classifier; inference reuses `_infer_topic(text, language)` /
`_infer_model(text, language)` (both **require `language`**). May import `app.*` + `orchestrator.*`
(it's api-layer).

### Route — `POST /projects/{id}/mid-journey-import`

(Distinct path — `chat.py:271` already owns `POST /projects/{id}/import` for the M2 artifact-commit
flow.) Authed (`Depends(current_user)` + ownership: `project.user_id == user.id` else 403), POST-only.
Steps:
1. Gather the project's uploads' extracted text (the uploads flow already writes `extracted.txt`
   per upload); **neutralize** each via `agent/guardrails.neutralize_document_text`.
2. `import_existing_work(files, language)`.
3. Commit each evidenced slice via `DbProjectStateStore.commit_slice`, **in `MODULES` order**
   (so downstream `needs_review` isn't spuriously raised — downstream modules are still `locked`
   when each commits), `confirm_done=False` (imported work is *in progress* until the student
   confirms).
4. **Set focus to the first NOT-imported module** (`next(m for m in MODULES if m not in slices)`,
   else the last) — this is what fixes "always M1": importing M1+M3 lands focus at M2, not M1.
   The route writes `Project.focus` directly (api-layer DB write).
5. Return `{imported, ambiguous, unreadable, focus}`.

### UI

`/new` (already drop-first) shows an "importing your work…" state then a summary card: "Imported:
M1 topic, M3 model, M5 ch.1–2 · You're at M4 · Next: run your analysis" + ambiguous items to
confirm.

## Data flow

```
/new upload → POST /projects/{id}/mid-journey-import (authed)
  → server extracts + neutralizes upload text
  → import_existing_work (classify + infer, api-layer)
  → commit_slice per evidenced module IN ORDER (in_progress)
  → focus = first not-imported module → summary card (activation)
```

## Error handling

- Best-effort per file: unreadable/garbled uploads listed under `unreadable`, never block import.
- Only evidenced slices commit; a slice that can't commit is skipped and NOT reported as imported.
- Ambiguous inferences returned for the agent to ask about, not silently written.
- Route is idempotent-ish: re-import merges (commit_slice overwrites owned keys).

## Testing

- `import_existing_work`: proposal PDF → M1 (+M3 if a model is inferable); analysis output → M4;
  unreadable → `unreadable`. Inference stubs use the **real 2-arg signature** `(text, language)`.
- Route: authed + ownership (401/403); stubbed `import_existing_work` → commits happen in MODULES
  order, `Project.focus` = first not-imported (importing M1+M3 ⇒ focus M2, NOT M1); imported list
  only includes slices that actually committed.
- Earned-gate: an empty/garbled chapter does not mark M5 done.
- api tests via `./run.sh`.

## Migration / rollout

1. `api/app/import_work.py` (classify + infer, api-layer).
2. `POST /projects/{id}/import` (auth + ownership + server-side extract/neutralize + ordered
   commits + focus).
3. `/new` UI summary card.

## Dependencies

- `app.partner_report_service` inference, `app.pdf_extract.extract_pdf_text`,
  `agent/guardrails.neutralize_document_text`, `app.deps.current_user`.
- **F2** (roadmap `derive_substep`/`next_action`) for the summary/next-step — the route only sets
  focus + status, the agent narrates. (Soft dep: import can land before F2; the card is richer with it.)
- **Not** dependent on F0 (imports go into owned module slices, which already round-trip).
