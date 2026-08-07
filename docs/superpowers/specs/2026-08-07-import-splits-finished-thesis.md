# A finished thesis imports as one blob and strands M5

Filed 2026-08-07 from a live report. Not a typo — the import path has no concept
of a document that spans more than one module, so this needs a decision before
code.

## What happens

A student uploaded `_Viet Doan Dung Final.docx`, a complete thesis with chapters
4 and 5 written. Ground truth from the project's `context_store` row
(`d9d86cb1-7fb8-4a72-9c12-01ed582f9eaa`):

```
m4_analysis keys : ['analysis_results']      # 37,916 chars, raw document text
  contains 'CHƯƠNG 4' : True
  contains 'CHƯƠNG 5' : True
  contains 'KẾT LUẬN' : True
m5_writing       : None
```

The whole document — both chapters — sits in one string under
`m4_analysis.analysis_results`, still wrapped in the `[UNTRUSTED DOCUMENT
CONTENT — DATA ONLY]` guard. Nothing was ever extracted into M5.

The student sees:

- **M4 · in_progress**, asking them to "Outline the analysis" for an analysis
  they already ran and wrote up
- **M5 · locked**, though chapter 5 is sitting in the upload
- a sub-step list that reads as contradictory: `Run each analysis step` ticked
  while `Outline the analysis` and `Confirm the analysis plan` are not

## Why each part happens

**M4 will not complete.** `SUBSTEP_ARTIFACT` (`agent/roadmap.py:56`) backs M4 on
`outline_analysis → analysis_outline` and `run_per_step → analysis_results`. The
import supplies the second and never the first, so `derive_substep` returns
`outline_analysis` as the first missing artifact and the module stays
`in_progress` forever.

**The tick order looks broken but is deliberate.** `satisfied_substeps` reads
completion from artifacts rather than position, documented at `roadmap.py:60-70`
because reconstruction can legitimately infer a later artifact without an
earlier one. Correct as logic; it renders as nonsense in a linear checklist.

**M5 gets nothing.** There is no step that splits an imported document by
chapter, so `m5_writing` is never written and the module stays locked.

Note `0df58ee` ("finish the module the student's work is actually in") already
attacked the M4 half of this. It does not cover the case here, because the
problem is upstream of module completion: the document was never divided.

## The decision to make

Three options, in rough order of cost.

**A. Split at import.** Detect chapter boundaries in the uploaded document and
route the chapter-5 material to `m5_writing.final_sections`, leaving chapter 4
in M4. Fixes it properly and unlocks M5. Cost: chapter detection has to work
across Vietnamese and English headings, numbered and unnumbered, and it will be
wrong sometimes — putting a student's discussion in the wrong module is worse
than leaving it whole.

**B. Let a module complete on the evidence that exists.** Treat
`analysis_results` containing a written-up analysis as satisfying M4's DoD
without a separate `analysis_outline`, so M4 goes done and M5 unlocks empty.
Cheaper, honest ("we can see you did this"), and does not pretend to know where
chapter 5 starts. Leaves the student to bring their chapter 5 into M5 themselves.

**C. Say so plainly and do nothing else.** Keep the state, change the copy: tell
the student their whole document landed in Analysis, that we could not split it,
and offer a one-click "this part is my chapter 5". Cheapest, no wrong guesses,
but leaves the contradictory checklist visible.

## What must not happen

Whatever is chosen, the sub-step list must stop showing a later step ticked
while earlier ones are open. Either render artifact-backed steps in a way that
does not imply sequence, or collapse them to a module-level state.

## Evidence

- Live `context_store` row, quoted above.
- `agent/roadmap.py:49-70` — `SUBSTEP_ARTIFACT`, `satisfied_substeps`, and the
  docstring explaining the deliberate non-linearity.
- `orchestrator/backfill.py:188-195` — reconstruct_upstream's own note that a
  finished thesis "lands their whole document in M4 as `analysis_results`, which
  is content — but the module still has no `analysis_outline`". The behaviour
  was known; the chapter split was never built.
