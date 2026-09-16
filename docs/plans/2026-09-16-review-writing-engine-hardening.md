# Review and writing engine hardening — 2026-09-16

## Scope and decisions

Follow-up to the H1–H9 audit: fix the product engines, preserving existing user prose and project state. Astra planned the boundaries; Terra implemented coherence and composition. No project DB writes, regeneration, deployment, or new statistical computation was performed.

Review must distinguish a provably wrong number from an unresolved attribution and from missing structured evidence. Writing must reuse that validator rather than adding a separate, conflicting interpretation of project state.

## Changes

- Registered M3 paths and their code/display aliases identify numeric claims, even without an H label. A unique path within the same paragraph can connect the result sentence to its hypothesis. Paragraph boundaries and MGA/group-difference context prevent borrowing unrelated coefficients.
- p-value operators remain operators; persisted upper bounds are not interpreted as exact values. Hard findings require a contradiction with the stored evidence.
- Known subgroup analyses are excluded from pooled-result comparison instead of being emitted as repeated author errors. Truly ambiguous multi-path claims remain advisory with a quoted passage.
- A pure shared grounding checker detects explicit claims that diagnostics passed when the relevant structured numeric evidence is missing. It distinguishes HTMT from Fornell–Larcker and ignores theoretical criteria or acknowledgements of missing data. This does not perform OCR of source report images or prove arbitrary semantic claims.
- Composition and rewrite prefer canonical analysis results and receive M3 hypothesis/construct definitions. After prose cleanup, hard numeric contradictions or explicit unsupported diagnostic assertions trigger at most one corrective model call. Unresolved or empty/stub corrections return `CompositionGroundingError` findings. The assembly/export adapter does not hide this error behind generic fallback prose.
- Assembled/preserved chapters are checked without silently rewriting imported work. Existing direct export behavior is not a promise that all prior prose has been repaired.
- Semantic review receives separate Results/Conclusion excerpts and canonical definitions rather than only the beginning of the thesis. Model judgments remain advisory; quoted evidence must occur in the actual draft.
- Coherence findings retain code, chapter, hypothesis, observed/expected values, and quoted evidence. Vietnamese presentation explains the action required. The editor displays the passage and replaces repetitive generic “how will you fix this?” questions with specific evidence questions.

## Verification

- Read-only replay against project `500319a8-5a06-47bf-bfd8-3ef921b36184` distinguishes the existing prose from the original false H1–H9 coverage warnings.
- A deep copy of that project with the first Chapter 4 `β = 0,257` changed to `β = 0,999` produces a hard H1 finding with expected `0.257`; the original database remains unchanged.
- A composition integration test uses the real validator and a mocked model: the wrong path coefficient triggers a second generation and the corrected coefficient succeeds. Other tests cover retry exhaustion, empty correction, rewrite, preserved prose, unsupported metrics, subgroup exclusions, and English/Vietnamese criterion descriptions.
- No live LLM semantic judgment or full thesis regeneration was run for verification; model-call control flow is tested with mocks.
- Final verification: 103 coherence/grounding/composition tests, 83 review/API/editor tests, and 7 ReviewPanel tests passed. `git diff --check` passed. Python tests with separate `tests` packages were run in separate invocations to avoid pytest package-name collisions.
- Final real-project replay: zero hard findings; four advisory findings (one multi-path attribution limit and three unsupported diagnostic assertions). No false H1–H9 coverage or managerial-language direction warnings remain in this replay.

## Existing test limitations

The workspace already contains unrelated TypeScript errors in `ChatInput.test.tsx` and `ChatPane.test.tsx`. Two state-tool tests also seed M3 without a model satisfying the current `m3_model_required` guard, so their setup is rejected before the behavior they intend to test. A broader inline suite has an existing citation-label expectation of `Anonymous` while the current fallback is `Anon`. Those unrelated fixtures are not changed here; the complete repository suite is not claimed green.
