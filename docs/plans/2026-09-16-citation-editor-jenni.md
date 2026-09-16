# Citation, review, and editor improvements — 2026-09-16

## Scope and evidence

This is an implementation plan based on the current dirty worktree, the root agent's Jenni browser observations, and the parallel read-only code audit. Preserve the existing changes. The planner has inspected repository code, not independently reproduced Jenni's UI. No implementation is included in this document.

Observed in Jenni: Cite at the cursor opens All / Discover / Library; query, sort and filter controls; results show title, authors, actual venue and year, an excerpt expandable with See more, Cite, Save, and Open quote opening a PDF side view. The AI proposal surface has a diff, explanation, Replace Selection, Insert below, Try again, and Discard. Review home exposes Claim confidence, Peer review, Source Quality, Tone, Proofread, and access to existing results.

Root subsequently observed Claim confidence results after an initial browser timeout: counted categories Unsupported, Weakly supported, Misrepresented, Contradicted, Overstated, and Unverifiable. Review Changes opens anchored individual suggestions (observed 1/136) with Prev/Next, Accept/Reject, Accept All/Reject All, and Resume editing. A card explains why a claim is unsupported, shows proposed source metadata, labels its excerpt ABSTRACT, and offers View DOI. No changes were accepted, and the correctness of those classifications or bulk-accept behavior was not tested. These observations do not establish equivalent capabilities in DoThesis and are not a requirement to copy bulk acceptance.

Already present in DoThesis's dirty worktree: Library / Find papers citation search, three-provider search, M2 reference addition, proposal diff and explanation, replace/insert/retry/discard controls, five review actions and findings. These are the baseline, not new deliverables.

Proposed here: make that workflow reliable and truthful before adding more surface area. Provider metadata establishes a paper record; it does not establish that a paper supports the student's claim. The existing abstract is an abstract, not a located quotation or full-text evidence.

## Priority 0: make citation and proposal actions correct

### Backend ownership — Terra backend

Files: `api/app/routers/m5_editor.py`, `orchestrator/tools/m5_inline.py`, narrowly needed citation validation helpers in `orchestrator/tools/m5_writing.py`, corresponding API/orchestrator tests. Edit relevant M2/M5 skill instructions first when behavior changes. Coordinate shared helpers with frontend's wire contract before coding.

1. Unify author formatting: canonical M2 `authors: list[str]` must produce the same display/citation label in list, search, add, canonical citation generation, and validation. `build_citation_text` currently reads only `author`, so a valid canonical source becomes Anonymous. Preserve legacy singular `author` support; do not create a second incompatible surname convention.
2. Use paper identity for IDs and reference-pool deduplication: normalized DOI first, otherwise normalized title plus bibliographic metadata. Existing `_reference_id` and `_collect_reference_pool` collapse distinct works by the same author/year. Keep all distinct papers selectable. Never let a stored source's arbitrary `id` override the calculated wire ID.
3. Compatibility: continue accepting a legacy author/year ID only when it identifies exactly one distinct paper. An ambiguous legacy ID must produce an explicit conflict, not choose the first source. Existing author/year prose remains readable; ambiguous text citations must not be given a guessed source link or counted as unique evidence. Do not invent a/b year suffixes without a complete disambiguation/export strategy. Existing pending proposals retain their text; new proposals carry the stable paper ID.
4. Verify the selected identity before adding it: DOI requests must resolve to the same normalized DOI; title fallback must match the requested title under a conservative normalization. Reject unrelated first search results. A returned title alone is insufficient verification. Preserve idempotent Save using the same identity key, handle `commit_slice` failures, and report success only after a successful M2 commit. Search/list stay read-only.
5. Separate metadata provenance from support assessment. Remove `verified = bool(doi)` as an assertion of verification. Return real title/authors/venue/year, full abstract and preview, provider, safe source URL, and a narrowly defined metadata status only if supported by the lookup. No claim-support badge or confidence number based solely on topical overlap, DOI presence, or citation count.

Acceptance checks: two papers sharing author/year remain distinct and cite the selected ID; canonical authors never become Anonymous; duplicate DOI Save is idempotent; wrong DOI/title fallback is rejected without a state write; failed commit cannot return a successful added record; provider exceptions can still yield partial results.

### Frontend ownership — Terra frontend

Files: `web/app/components/editor/ChapterEditor.tsx`, `CitePopover.tsx`, `SourcesRail.tsx`, citation extensions only as necessary, relevant component tests. Do not duplicate existing pending-edit features.

1. Apply successful accepted proposal prose to the mounted TipTap editor. Current accept only revalidates SWR and `initialProse` is used at construction, so accepted edits can disappear from the pending list without appearing in the document. Preserve markdown/media/token handling and avoid a synthetic autosave loop. Guard against overwriting text entered while the request was in flight; use the response only against the matching editor baseline, otherwise show a conflict/reload path that preserves local content. Surface non-409 errors instead of swallowing them. Disable duplicate in-flight actions.
2. Make result titles inspectable, and provide separate explicit Cite and Save actions. Save adds to M2 and keeps the picker open; Cite uses an existing library item or adds then creates the current pending citation proposal. Failed add must never invoke citation insertion. Revalidate the source rail after a successful add.
3. Show and expand the actual abstract, label it Abstract, and provide a safe external source link when available. Missing abstract stays missing. This is a useful evidence-inspection step; do not label it Quote or implement a pretend PDF reader.
4. Keep library filtering independent of selected-text search. Selected prose can seed Discover; switching to Library must not hide everything because the entire claim became its filter. Distinguish loading, failed load, untouched search, and empty results. Prevent stale search responses from replacing a newer query/project's results.
5. Replace 'DOI verified', 'Verified link', and 'ranked for this claim' with accurate labels such as DOI, Open source, and Relevance to search. Explain briefly that the abstract should be checked before citing. Preserve actual venue when present; never display provider as venue.
6. Repair source navigation only for uniquely identifiable citations. Audit notes `CitationMark` is installed but not applied in production, while `CitationHighlight` contains no reference ID. Pass real identities through the existing path where possible; ambiguous author/year text should open matching sources or remain unlinked, never silently jump to an arbitrary paper.

Acceptance checks: Save leaves the picker open and never inserts; Cite creates exactly one proposal; expand/open does not cite; selected-text seed does not empty Library; failed load/search/add shows recovery; accepted replacement and insertion appear immediately; stale/in-flight local changes are preserved; a citation jump targets the correct source or explicitly handles ambiguity.

## Priority 1: keep review results useful and honest

Frontend owner extends `ReviewPanel.tsx` after priority 0; backend owner adds scope metadata only if needed, without a second reviewer.

- Retain the latest result for each kind when returning to review home, and expose View results. A bounded in-session cache is enough for this increment; do not imply database persistence. Reset it on project change. Do not use browser local storage for thesis findings.
- Show rerun failures in the results view, preserve the previous result, and reset per-result manual resolved flags when a new review ID arrives. A manually checked item is not automatically verified as fixed.
- Use the actual review kind in Ask agent prompts (currently hard-coded to Claim confidence).
- Describe actual coverage: Claim confidence currently combines citation/reference consistency with numerical coherence; it does not test whether full-text sources support each claim. Source quality currently checks metadata and optional DOI lookup; it does not detect retractions or establish peer-review status. Display applicable limits and lookup status, especially when no network DOI checks ran. Do not market these actions as Jenni feature parity.
- Replace the cycling fake phase/progress counter with an indeterminate status unless backend progress is real. Review results are a snapshot of the last saved thesis; do not imply unsaved prose was reviewed.

Acceptance checks: run A → home → View A restores the result; run B preserves A; rerun failure is visible without clearing results; new results reset old local completion marks; project changes do not leak findings; descriptions match the deterministic/LLM checks actually run.

## Invariants and scope cautions

- All new durable literature/prose state changes must use the owning module's `commit_slice`; reads must not shift focus or mark modules done. M2 additions can flag downstream work, and UI should not imply that saving metadata has verified claims.
- Baseline discrepancy discovered during planning: chapter PATCH and proposal acceptance directly mutate `cs.m5_writing` and commit the DB session. They do not currently use the documented M5 commit boundary. Do not describe the existing editor as fully invariant-compliant. If editing those write paths, route prose changes through the supported M5 commit boundary, preserving coherence validation, chapter mapping, pending edit metadata, and unrelated chapters. Investigate store behavior before replacing the path; avoid a broad storage rewrite disguised as a UI change.
- Insertion proposals have an empty old-text span; the current stale-offset comparison cannot detect every intervening edit before the insertion point. If accept safety is touched, capture and validate a document revision/snapshot for new zero-width proposals rather than relying only on an empty slice comparison.
- Preserve POST authenticated reads and existing authorization ownership checks. Existing PATCH autosave is a legacy exception in the inspected code; do not introduce new GET mutations or token URLs.
- Add short reasoning comments for non-obvious decisions, per AGENTS.md. Never revert unrelated dirty files.

## Deferred work

Full PDF ingestion/rendering and page-anchored quotes; semantic claim/evidence scoring; retraction/preprint detection; persistent review history; All-tab aggregation; provider-wide sort/year filters; full APA same-author/year disambiguation. These require real data contracts, provenance, and separate validation. Semicolon-group citation parsing is a bounded follow-up if the backend owner can cover it with regression tests; avoid blocking priority 0 on a complete citation parser rewrite.

## Integration validation

Run targeted reference/search/add/cite/accept API tests, citation formatting/validation tests, and editor component tests covering the failure/concurrency cases above. Root should run the available frontend typecheck and a local browser smoke flow: search → inspect abstract → Save → Cite → accept → click source, then review → home → reopen results → rerun error. Check the final diff against the initial dirty baseline. Report any unimplemented invariant repair or browser limitation explicitly rather than claiming complete parity.

## Delivered and verified

Planning used Astra; backend/frontend implementation used Terra, with Luna updating stale test mocks and expectations. Existing uncommitted work was preserved.

- Added DOI-first identities, bibliographic fallback identities, legacy ambiguity handling, exact add verification, canonical author formatting, and failure-aware commits. Search candidates do not claim verification merely because a DOI is present.
- Split grouped citations during validation and report ambiguous references separately. Editor prose writes now call the M5 commit boundary and the existing coherence validator. Revision fingerprints protect stale proposal/application requests; they are optimistic preconditions, not transactional compare-and-swap across simultaneous database writers.
- Separated Save from Cite, added expanded abstracts, source links, saved feedback, independent library/search queries, truthful provenance labels, and error states. Provider names are not presented as journal venues.
- Accepted proposals update mounted editor content and reconcile the save queue while retaining newer local typing. Review results can be reopened within the mounted review session; rerun errors retain prior results, and manually reviewed findings are not described as automatically fixed.
- Root validation: 124 editor tests across 24 files and 88 targeted backend tests passed. Additional final request-contract regressions are run separately. Typecheck reports only the same pre-existing errors in `ChatInput.test.tsx` and `ChatPane.test.tsx`; no new editor errors. `git diff --check` passed.
- Live Chrome smoke: searched a real tourism paper, expanded its abstract, and saved an already-present source without duplicating it or inserting a citation. Re-running Claim confidence removed two false grouped-citation findings (11 findings became 9; genuine coherence findings remained). Back → View results restored the same result without rerunning. Existing user proposals were not accepted/rejected during smoke; acceptance and conflict behavior were checked in tests.

Limits: full-text claim support, PDF page quotes, retraction detection, and persistent review history remain outside this increment. Plain-text citations do not gain a new durable source sidecar; navigation requires an existing real reference ID, and ambiguous prose is never linked to a guessed source. These limitations are not represented as completed Jenni feature parity.
