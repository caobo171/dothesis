# Mid-Journey State Import Design (F12)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation (audit CRITICAL):** Most paying students arrive **mid-thesis** — topic approved,
data collected, or three chapters written. Because DoThesis state is *earned*, today's agent has
no way to reflect work done elsewhere and would insist on starting at M1. This is the biggest
tagline gap ("goes with your journey" must mean *joining* a journey in progress) AND the missing
first-run activation moment. The `partner_report_service` inference code already does ~70% of the
work.

## Problem

A student uploads their proposal + two chapters + an SPSS output file and expects the agent to
"catch up." Instead the roadmap shows everything `locked` at M1. The first session — the make-or-
break activation moment — feels like the tool ignores everything they've done.

## Goals

- **Import from uploads:** classify the student's existing material (proposal, chapters, dataset,
  analysis output, questionnaire) and **infer per-module slices**, committing them as *earned*
  state so the roadmap starts where the student actually is.
- **Earned, not narrated:** state is derived from the *artifacts* (the uploaded evidence), then
  written via `commit_slice` — consistent with "state is earned." Ambiguous items are asked, not
  assumed.
- **Activation:** the first `/new` session ends with "here's where you are, here's your next step"
  — the aha — instead of a blank M1.

## Non-goals

- Not a plagiarism/authorship check (that's the integrity feature).
- Not importing *quality* — imported chapters may be weak; F3 grades later.
- Doesn't fabricate missing modules — only what the uploads evidence.

## Design

### Import pass (extends `/bootstrap`)

`import_existing_work(files, notes) -> dict` in `agent/import_work.py`:
1. **Classify** each upload (proposal / chapter-N / questionnaire / dataset / analysis-output)
   via extension + a cheap LLM classifier on extracted text (reuse `pdf_extract`, the docx path,
   and prompt-injection neutralization from `agent/guardrails.py`).
2. **Infer per-module slices** reusing partner inference (`_infer_topic`→M1, `_infer_model`→M3,
   analysis text→M4) + chapter parsing → M5 `final_sections`, questionnaire → M3 `instrument`.
3. Return `{slices: {M1:{…},…}, evidence: {module: filename}, ambiguous: [...]}`.

### Commit as earned state

The bootstrap skill commits each inferred slice via `commit_slice(module, writes, reason=
"imported from <file>")` — so status flips to `in_progress`/`done` **because a real artifact backs
it** (the artifact is the evidence the done-gate requires). Downstream `needs_review` propagation
works as normal. Ambiguous items → the agent asks before committing.

### Focus + next step

After import, `focus` is set to the first module still incomplete (via F2 `derive_substep`), and
the agent opens with the roadmap + next action — the activation aha.

### UI

The `/new` flow (already "drop-first") gains an "importing your work…" progress state and a
post-import **summary card**: "Imported: M1 topic, M3 model, M5 ch.1–2 · You're at M4 · Next:
run your analysis."

## Data flow

```
/new: drop proposal + chapters + output → import_existing_work
  → classify → infer slices → commit_slice per evidenced module (earned)
  → focus = first incomplete → roadmap + [NEXT] → activation summary card
```

## Error handling

- Best-effort per file: an unclassifiable/garbled upload is listed as "couldn't read" and skipped,
  never blocks the import.
- Only evidenced slices are committed; the done-gate still applies (empty slice can't be `done`).
- Ambiguous inferences are surfaced as questions, not silently written.

## Testing

- Classifier: a proposal PDF → `proposal`; an SPSS output → `analysis-output`.
- Import: fixtures (proposal + a results file) → M1 + M4 slices inferred; committing flips M1→
  done / M4→in_progress; `focus` = first incomplete.
- Earned-gate respected: an empty/garbled chapter does NOT mark M5 done.
- Ambiguous case → returned in `ambiguous`, not committed.
- api tests via `./run.sh`.

## Migration / rollout

1. `import_existing_work` (classify + infer, reusing partner inference).
2. Bootstrap skill: commit evidenced slices + ask on ambiguous + set focus.
3. `/new` UI: import progress + summary card.

## Dependencies

- `partner_report_service` inference helpers (`_infer_topic`/`_infer_model`), `pdf_extract`,
  `agent/guardrails.py`.
- **F2** (roadmap `derive_substep`/`next_action`) for focus + the activation summary.
- **F0** (persistence) is not required (imports go into module slices via `commit_slice`).
