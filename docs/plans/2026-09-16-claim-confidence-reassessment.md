# Claim confidence reassessment — Jenni live inspection

## User intent

The user pointed out that Jenni actively finds papers and enriches citations across a draft. This capability was not delivered by the earlier citation integrity/editor work. Do not label the existing DoThesis feature equivalent to Jenni claim confidence.

## Direct observations

Inspected the existing Chrome document `https://app.jenni.ai/editor/6EPkRBl2fORxHim7mxrx` without accepting/rejecting any changes or triggering another review.

- Claim confidence result: 122 suggestions: Unsupported 80, Weakly supported 28, Misrepresented 11, Overstated 3; Contradicted and Unverifiable show none.
- Home badge separately shows45; do not equate that badge with all122 findings. The exact relation was not established.
- Document References displays Sources98. This is the current document source count, not proof that one review discovered98 new sources.
- Unsupported suggestion: a claim about popularity alone being insufficient for influencer effectiveness is paired with Hill & Qesja (2022), “Social media influencer popularity and authenticity perception in the travel industry”, Service Industries Journal, DOI10.1080/02642069.2022.2149740. The card explains relevance, presents source metadata/excerpt, and has Accept/Reject.
- Misrepresented suggestion: Jenni identifies a different passage from the same source that specifically addresses cost/information in an intention–behaviour gap claim. It shows the excerpt and Open quote. Finding a better passage is distinct from simply adding another DOI.
- Existing document includes many newly-looking inline citation chips across conceptual and methodological sentences. UI observation alone does not establish when each was added or that every proposed citation correctly supports its claim.

## Verified DoThesis gap

`quality/rubric.py:focused_review`, kind claim_confidence, currently returns deterministic citation checks plus coherence_dimension. It performs no per-claim external paper retrieval, semantic evidence assessment, or source-backed edit proposal generation.

Search already exists separately in `api/app/routers/m5_editor.py`: multi-provider candidates, DOI/bibliographic deduplication, title/abstract overlap ranking. The cite endpoint creates a PendingEdit for an already selected library reference. At inspection time, these building blocks were not connected into claim confidence. The editor implementation below now connects them.

## Required behavior for the next implementation

1. Scan all selected chapters in bounded chunks and identify addressable claims that benefit from literature support. Exclude the author's own project description, hypotheses being proposed, and actual measured results; literature must never substitute for missing study data.
2. Generate targeted search queries per claim/group, including English equivalents for Vietnamese claims. Reuse library sources where supported and retrieve additional candidates from scholarly providers. Cache/reuse queries across equivalent claims; display processed/total coverage and provider failures.
3. Deduplicate verified bibliographic records, then assess actual available evidence per claim: abstract versus retrieved full-text passage, supporting versus partial/contradictory. DOI validity and title similarity alone cannot establish support.
4. Return anchored suggestions containing original sentence, classification, Vietnamese rationale, candidate source metadata, evidence excerpt/provenance, and proposed citation insertion or minimally revised wording.
5. Present each as a reviewable diff with navigation and Accept/Reject. On acceptance, deduplicate/register the reference through M2 commit_slice and update only the anchored M5 text through its commit boundary, rejecting stale edits. Review/search itself must not alter the thesis.
6. Measure claim coverage and evidence relevance, distinct verified sources, unresolved claims, and accepted edits. Do not optimize raw citation count or automatically attach multiple weakly related sources to every sentence.

## Implementation delivered

- `quality/claim_confidence.py` extracts addressable scholarly claims from canonical chapter snapshots, searches per claim, ranks existing and fresh sources together, and requires literal retrieved quotations plus semantic support before proposing a citation. Unresolved/partial evidence remains visible and cannot be accepted as a citation.
- `api/app/routers/claim_reviews.py` provides start/latest/next/accept/reject, bounded persisted review snapshots, query/source caching and verified metadata. Accept registers M2 sources and edits M5 through `commit_slice` in one database transaction. Known accepted edits rebase remaining anchors; external prose changes fail closed.
- Editor Review opens the evidence panel: Vietnamese rationale, original/proposed sentence, bibliographic source, abstract/full-text label, chapter navigation, Accept/Reject, stop/resume/restart and saved results. Accepted edits refresh the editor, source rail and export-dirty indicator.
- Astra designed the workflow; Terra implemented engine/frontend, with root integration and final corrections.

## Validation and limits

- Focused automated checks: 20 backend/state, 12 engine and 33 frontend tests passed. Final changes were rerun against their affected suites.
- Live retrieval/LLM smoke with Hill & Qesja (2022), DOI `10.1080/02642069.2022.2149740`, produced a literal abstract quote, Vietnamese explanation and an actionable citation proposal.
- Live Chrome smoke on the supplied project processed 3,646/134,605 characters (1/37 chunks), returned two source-backed findings (one new citation opportunity and one already-supported citation), and stopped. No proposal was accepted and no thesis citation was inserted by this smoke. The cached partial review can be reopened/resumed.
- The initial live scan revealed extraction bias toward already-cited sentences. The prompt was corrected to explicitly include uncited claims; replaying extraction on the same 3,646-character snapshot found 23 claims without anchor warnings. New snapshots use at most 1,000 characters per chunk to keep per-claim retrieval batches manageable.
- Final live Chrome smoke with the corrected extractor and smaller batches: 1/166 chunks processed, five claims assessed against five distinct verified sources, two actionable citation proposals and three partial-evidence findings. The review is paused and saved; all five suggestions remain pending. No thesis changes were accepted.
- This delivers source discovery and evidence-backed insertion, not full Jenni parity. Current provider retrieval is principally abstracts; no general PDF full-text retrieval is claimed. It does not automatically rewrite overstated claims or independently classify all existing citations as misrepresented/contradicted. Model extraction/semantic judgments remain fallible; coverage reports processed text and extracted claims, not proof that every factual sentence has been verified.
- Reviews run while the panel is open, one request per chunk; resume reuses saved progress. Cache retention is seven days and at most five review snapshots per project/user. A full-thesis live review was deliberately not run during validation.
