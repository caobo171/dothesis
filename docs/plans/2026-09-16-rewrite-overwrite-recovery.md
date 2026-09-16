# Rewrite overwrite incident — 2026-09-16

## Confirmed failure

Project `500319a8-5a06-47bf-bfd8-3ef921b36184`, thread `c10f6d13-4af0-4068-8cc9-bf03a89e5331`:

- The user requested rewriting and exporting the final thesis.
- Chat post-processing incorrectly substituted a questionnaire/M3 save instruction when export succeeded without an externally visible commit tool call.
- Another deterministic message instructed the user to request an overwrite. The user followed it.
- At 08:15:53 UTC, five complete chapters were replaced by prose of 110–179 characters. Both canonical chapters and legacy final_sections were affected.
- No durable VersionHistory rows existed for the project before recovery.

## Changes

- State-level M5 validation rejects severe summary replacement before snapshot/status mutation, including changes between legacy and canonical layouts.
- `rewrite_thesis` composes full replacement chapters in memory with force_recompose, checks completeness/grounding and current chapter hashes, commits once, verifies persisted hashes, then exports persisted content. A generation/validation failure does not clear the previous draft.
- Export composition stops on persistence failure instead of exporting an unsaved draft.
- Runtime carries compact typed persistence evidence independently of truncated previews and recognizes rewrite download artifacts.
- Chat uses content hashes, distinguishes export/save/rewrite, removes special retry phrases and unrelated questionnaire instructions, and inherits save intent only from user messages.
- Database slice writes and durable version snapshots share one transaction. Legacy slices receive a pre-change snapshot; existing rows are locked while seeding history. Failure to insert history rolls the mutation back.

The generation-time hash check detects changes made while composition runs. It is not a database compare-and-swap spanning the final read and commit; that narrow race remains a limitation.

## Recovery performed

Recovered through DbProjectStateStore.commit_slice, not direct database mutation. Restored exact chapter Markdown and final_sections from the project’s earlier read_slice snapshot (00:53:23 UTC). Prose lengths after reload:

| Chapter | Characters |
|---|---:|
| Introduction | 21,712 |
| Literature review | 61,162 |
| Methodology | 24,700 |
| Results | 18,167 |
| Conclusion | 8,864 |

All five original image paths exist. Deterministic coherence found no hard numeric contradictions against current M4. The restored draft is the previous full draft, not a newly generated thesis or a claim that all review findings are resolved.

The last good DOCX (08:13:55 UTC) remains intact, as do the stored export artifacts. Its prose closely matches the recovered snapshot after citation/rendering transformations. Some later edits may be absent in the restored editor (one identifiable later insertion was “Testing edit”). A DOCX-derived alternative was retained alongside the exact snapshot. No original chat messages were rewritten.

Recovery files are retained under the project workspace `recovery/2026-09-16-summary-overwrite/`: pre-recovery state, exact snapshot, DOCX-derived alternative, last good DOCX, and recovery verification. Durable history now contains pre-recovery and restored snapshots.

## Validation

Focused writer/coherence/composition/export/runtime tests: 125 passed. Chat routing and database persistence suite: 37 passed. Final focused M5 guard/rewrite selection: 20 passed (30 unrelated tests deselected). No paid LLM regeneration was run during recovery; this work verifies deterministic boundaries and restores the existing draft. Local API health returns ok.
