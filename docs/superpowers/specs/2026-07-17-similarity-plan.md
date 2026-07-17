# Similarity & Quote-Hygiene Self-Check — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-similarity-design.md` (read it first — the algorithm §4, thresholds §5, hygiene table §6, severity policy §7, and report schema §8 are normative there; this plan only sequences them).
**Executor notes:** All paths relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–3 are pure functions with zero wiring; Phase 4 is the only task that edits the shipped rubric — its existing suite must stay green in the same task. Tests live in top-level `tests/` (`pytest.ini` `testpaths = tests`); offline only — no network, no LLM calls, no `integration` marker needed.

**Hard constraints (from the design):**
- `quality/similarity.py` is pure: stdlib (`re`, `unicodedata`, `hashlib`) + `agent.coherence.segment_sentences` only. No LangChain, no orchestrator import at module scope, no I/O, no clock, no `random`, and **never** builtin `hash()`.
- Every finding this initiative emits is `severity: "soft"` — enforced by test (Task 4.2), not comment.
- Entry points (`check_similarity`, `similarity_report`) never raise.
- No report field ever carries more than 160 chars of prose per span; `top_spans` ≤ 10; findings surfaced ≤ 15; `headline` is always `null`.

---

## Phase 1 — pure fingerprint core (`quality/similarity.py`)

### Task 1.1 — Normalization + tokenization with offsets
- **Files:** `quality/similarity.py` (new), `tests/test_similarity_core.py` (new)
- Tests first:
  - `normalize_tokens(text) -> list[(text, start, end)]`: NFC (a decomposed-Vietnamese input and its composed twin yield identical token texts — mirror `agent/coherence.py:48-49`), lowercase, punctuation→space, whitespace split; offsets index the **original** string (assert `original[start:end]` round-trips to the pre-normalization surface form).
  - Noise stripping (design §4.1), offset-preserving: `{{cite: A | Title Words Here | url}}` pills (syntax: `agent/runtime.py:359-364`) vanish from tokens; inline citations `(Nguyen, 2023)` / `(Tran, n.d.)` vanish from tokens but their spans are returned by a separate `citation_spans(text)` helper (regex duplicated from `orchestrator/tools/m5_writing.py:128` with a parity comment); lines after a `References` / `Tài liệu tham khảo` heading and bibliography-shaped lines (author-year + DOI/URL) drop; low-letter-ratio lines (markdown table rows) drop.
  - Parity test: the local citation regex and `orchestrator.tools.m5_writing._CITATION_REGEX` produce identical matches over a shared fixture list (this one test may import orchestrator — it's a test, not the module).
- **Verify:** `python -m pytest tests/test_similarity_core.py -q`
- **Done when:** green; a subprocess `python -c "import quality.similarity"` succeeds with `langchain`/`orchestrator` absent from `sys.modules` (assert in a test, precedent: coherence plan Task 1.1).

### Task 1.2 — Shingling + winnowing
- Tests first:
  - `shingle_hashes(tokens, k=7)`: n−k+1 hashes; blake2b-8 based — assert a hard-coded expected hash for one known shingle (locks the algorithm; catches accidental `hash()` use), and byte-identical output across two subprocesses launched with `PYTHONHASHSEED=1` and `=2`.
  - `winnow(hashes, w=4)`: hand-computed expected fingerprint list for a small vector (build the vector from the chosen hash function's actual values, comment the derivation); rightmost-min tie rule asserted with a crafted tie; consecutive-window dedup.
  - **Guarantee property test** (design §4.3): seeded-random token sequences with a planted common run of exactly `t = w + k − 1 = 10` tokens → the two fingerprint sets always intersect; a planted run of `k − 1 = 6` tokens with otherwise-disjoint vocab → never detected.
  - Short-text fallback: 5–6 token source → one whole-text shingle; < 5 tokens → `[]`.
- **Verify:** `python -m pytest tests/test_similarity_core.py -q`
- **Done when:** green.

### Task 1.3 — Seed → extend → merge (`matched_spans`)
- Tests first:
  - `matched_spans(a_tokens, b_tokens, min_span) -> list[Span]` where `Span` carries token indices + original-char offsets on both sides and token length: a planted 30-token copy → exactly one span with exact boundaries; a hash-collision-style seed (equal hashes, different token text — construct via monkeypatched hasher) → discarded by extension; two runs separated by a 2-token gap → merged; by a 3-token gap → two spans; `min_span` filtering (11 tokens dropped at `min_span=12`).
  - Seed cap: > 500 seeds (a chapter equal to the source) → still one merged span, `truncated` flag surfaced.
  - Determinism: output list ordering is (a_start, b_start) sorted; two runs byte-equal.
- **Verify:** `python -m pytest tests/test_similarity_core.py -q`
- **Done when:** green.

### Task 1.4 — Performance smoke
- **Files:** `tests/test_similarity_perf.py` (new)
- Test: synthetic ~200k-token corpus (seeded, built in-test) — full tokenize+fingerprint+match across 6 chapters × 20 sources + 15 chapter pairs completes in **< 10 s** (`time.monotonic` bound; generous for CI). Mark nothing — it must run in the default suite.
- **Verify:** `python -m pytest tests/test_similarity_perf.py -q`
- **Done when:** green in < 10 s.

## Phase 2 — corpus assembly + comparisons

### Task 2.1 — Source-text and chapter extraction
- **Files:** `quality/similarity.py`, `tests/test_similarity_corpus.py` (new)
- Tests first:
  - `source_texts(source: dict) -> list[(field, text)]`: reads optional `abstract`, `key_claims` (strings, or dicts via `quote`/`claim`/`text` keys), `summary`, `title` in that order; the shipped title-only shapes (`orchestrator/tools/m2_literature.py:218-233`, `agent/tools/research.py:85-100`, `orchestrator/tools/domain_sources.py:108-118`) yield `[("title", …)]`; non-dict source → `[]`.
  - `source_label(source)`: first-author surname + year via the `_ref_citation_key` semantics (`orchestrator/tools/m5_writing.py:100-123` — duplicate the small surname logic with a parity comment; authors list, singular `author` fallback, "Anon").
  - Chapter resolution inside `check_similarity`: `final_sections` list and `chapters` dict shapes both resolve to canonical chapters (lazy-import `chapters_from_final_sections`, precedent `agent/coherence.py:286-303`); a References section is **absent** from the resolved set (`orchestrator/tools/m5_writing.py:1653-1655`); stub chapters dropped via `_is_stub_prose` semantics (`:1722-1729` — lazy import or local copy, decide once, comment).
- **Verify:** `python -m pytest tests/test_similarity_corpus.py -q`
- **Done when:** green.

### Task 2.2 — `check_similarity(context_store)` end-to-end pass
- Tests first (build small full context_stores, shapes per `agent/state.py:38,52`):
  - **Known-plant:** a 30-word span from a source's `abstract` pasted into the results chapter → one `similarity.source_overlap` raw match with the right chapter, source label, token count, ≤160-char excerpt.
  - **Paraphrase:** reworded content → no match.
  - **Intra-thesis:** 25-token paragraph in both results and discussion → `similarity.intra_duplication`; the same M3 hypothesis statement restated in both → exempt (design §5); 15-token duplication → below the 20-token intra floor, no match.
  - **Bibliography immunity:** reference list as a final_section + `{{cite:}}` pills carrying full titles in prose → zero matches.
  - Title-only corpus: matches against a long title still detected ≥ 12 tokens; `sources_title_only` counted.
  - Never-raise: `{}`, `None` slices, sources as strings → empty result, no exception.
- **Verify:** `python -m pytest tests/test_similarity_corpus.py -q`
- **Done when:** green.

## Phase 3 — quote hygiene

### Task 3.1 — Quote regions + citation adjacency
- **Files:** `quality/similarity.py`, `tests/test_similarity_hygiene.py` (new)
- Tests first:
  - `quote_regions(text)`: `"…"`, `“…”`, `«…»` pairs and markdown `>` blockquote lines; unbalanced quotes never crash and never swallow the rest of the document (cap region length ~1000 chars, comment why).
  - `adjacent_citation(text, span, sources)`: citation in the same sentence (via `agent.coherence.segment_sentences`) → cited; within 200 chars after span end → cited; none → uncited; `(Nguyen, 2023)` against the matching source record → `cited_to_source: true`.
- **Verify:** `python -m pytest tests/test_similarity_hygiene.py -q`
- **Done when:** green.

### Task 3.2 — Classification + finding copy
- Tests first — the four-row table from design §6, one test per row:
  - quoted+cited → **no finding**; quoted+uncited, unquoted+cited, unquoted+uncited → one finding each, `fix` copy matching the design's templates (assert the "quote it with a page number, or paraphrase" phrasing for the worst case, with the real token count and source label interpolated — the roadmap's own exemplar, `roadmap.md:336-337`).
  - Intra-duplication finding copy ("consolidate or rewrite"); no hygiene classification attempted for intra spans.
  - Every finding dict has exactly the rubric keys `issue`/`fix`/`chapter`/`severity` and `severity == "soft"`.
- **Verify:** `python -m pytest tests/test_similarity_hygiene.py -q`
- **Done when:** green.

## Phase 4 — rubric dimension (the only shipped-code edit until Phase 5)

### Task 4.1 — `similarity_dimension` + `score_thesis` wiring
- **Files:** `quality/rubric.py`, `tests/test_similarity_dimension.py` (new — mirror `tests/test_coherence_dimension.py` / `tests/test_source_verification_dimension.py` structure)
- Tests first:
  - Dimension shape `{name: "similarity", weight: 0.10, score, findings}`; score formula `max(0, 1 − 0.10·source_overlap − 0.05·intra)` over capped (≤ 15) findings; clean thesis → score 1.0, no findings.
  - Fail-open: monkeypatch `quality.similarity.check_similarity` to raise → dimension returns score with empty findings, no exception (pattern: `quality/rubric.py:430-452`).
  - Lazy import: `import quality.rubric` does not import `quality.similarity` (subprocess `sys.modules` check, convention `quality/rubric.py:27-31`).
  - `score_thesis` includes the dimension (after `coherence_dimension`, before the institution overlay, `quality/rubric.py:486-489`).
- Regression: full existing rubric suite green.
- **Verify:** `python -m pytest tests/test_similarity_dimension.py tests/test_coherence_dimension.py tests/test_source_verification_dimension.py tests/test_stats_validity_dimension.py -q`
- **Done when:** all green.

### Task 4.2 — Soft-only enforcement
- Test: over a context_store engineered to trigger every finding type (all four hygiene rows + intra), assert no finding from the similarity dimension has `severity == "hard"` and `score_thesis(...)["blocking"]` gains no entry from it (`quality/rubric.py:490`).
- **Verify:** `python -m pytest tests/test_similarity_dimension.py -q`
- **Done when:** green.

## Phase 5 — report surface + M5 skill copy

### Task 5.1 — `similarity_report`
- **Files:** `quality/similarity.py`, `tests/test_similarity_report.py` (new)
- Tests first — the design §8.2 schema exactly: `counts` keys present; `top_spans` ≤ 10, sorted by token length desc then (chapter, offset); `per_source` ≤ 20; excerpts ≤ 160 chars; `headline is None` asserted explicitly; `coverage_note` contains the not-Turnitin sentence and the with-text/title-only source counts; `truncated` flag propagates from the seed cap; deterministic across two runs; never raises on garbage stores.
- **Verify:** `python -m pytest tests/test_similarity_report.py -q`
- **Done when:** green.

### Task 5.2 — Attach to `export_docx`
- **Files:** `agent/tools/writing.py`, `tests/test_similarity_report.py`
- Tests first: the export tool's returned JSON gains a `"similarity"` key holding the report; a report failure (monkeypatched raise) leaves export **successful** with `"similarity": null` — advisory, never a gate (design §7); export behavior otherwise unchanged (existing writing-tool tests green).
- Implement: inside `export_docx` (`agent/tools/writing.py:36` factory), after a successful export build, lazy-import `quality.similarity.similarity_report`, try/except to `null`, attach to the return dict (alongside `artifacts`/`chapters`, `agent/tools/writing.py:274-283`). Note in a comment that the web run drawer renders this field (roadmap `:341-342`) — client wiring is a separate web change, out of scope here.
- **Verify:** `python -m pytest tests/test_similarity_report.py agent/tests -q -k "writing or similarity"` (adjust `-k` to the actual writing-tool test names found at implementation time; the full-suite gate below is authoritative)
- **Done when:** green.

### Task 5.3 — M5 skill copy
- **Files:** `skills/dothesis-m5-writing/SKILL.md`
- Add a short "Paraphrase & quote hygiene" section (≤ 12 lines, beside the existing coherence-gate note at `skills/dothesis-m5-writing/SKILL.md:138`): draft in your own words; when exact wording matters, quote + cite with a page number; the similarity self-check runs at review/export and flags unquoted verbatim overlap with the project's own sources and chapter-to-chapter duplication; it is a self-check against the project's own sources, **not** a Turnitin scan. Vietnamese-first tone consistent with the rest of the skill.
- **Verify:** manual read; `python -m pytest tests -q` still green (skills are prompt text, no code path).
- **Done when:** copy merged; full suite green.

## Phase 6 — follow-up (small, separable): persist source abstracts

Unblocks the chapter-vs-source check's real power (design §2.2 — abstracts are not persisted today). Each is a mapping-level change; land after Phases 1–5 or in parallel by a second executor.

### Task 6.1 — Scout mapping carries `abstract`
- **Files:** `orchestrator/tools/m2_literature.py`, its existing tests
- Test first: a Citation object exposing `.abstract` → mapped dict contains `abstract`; absent → key present as `None` (or omitted — match the mapping's existing style at `:218-233`).
- Implement: add `"abstract": _field(c, "abstract")` to the `scout_citations` mapping (the engine `Citation` already carries it — `engine/utils/citation_database.py:153,175`).
- **Verify:** `python -m pytest tests -q -k m2` (adjust to actual test module names)

### Task 6.2 — Crossref fallback + domain sources carry `abstract`
- **Files:** `agent/tools/research.py`, `orchestrator/tools/domain_sources.py`, `agent/tests/test_research_tools.py`, `agent/tests/test_domain_sources.py`
- Tests first: `_crossref_fallback` maps `abstract` (add `abstract` to the Crossref `select` list at `agent/tools/research.py:71`; note Crossref abstracts arrive as JATS XML — strip `<jats:…>` tags, test with a real-shaped fixture); `norm_source` (`orchestrator/tools/domain_sources.py:108-118`) passes through `p.get("abstract")`.
- **Verify:** `python -m pytest agent/tests/test_research_tools.py agent/tests/test_domain_sources.py -q`
- **Done when:** green; a similarity corpus test from Task 2.1 re-run against the new shape shows `sources_with_text` > 0 with no code change in `quality/similarity.py` (the optional-field design absorbs it).

---

## Final gate

- `python -m pytest tests -q` and `python -m pytest agent/tests -q` fully green.
- Grep re-check: `quality/similarity.py` contains no `import langchain`, no module-scope `orchestrator` import, no `hash(`, no `random`, no `time` beyond nothing (perf test owns timing).
- Read the design's §12 table against the shipped code — every row either implemented or explicitly deferred with a comment.
