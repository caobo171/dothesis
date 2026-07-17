# Similarity & Quote-Hygiene Self-Check — Design Spec

**Date:** 2026-07-17
**Initiative:** Roadmap #11 (`docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:324-345`; table row at `:41`)
**Vision anchors:** §3.8(c) similarity self-check (`2026-07-17-dothesis-vertical-agent-vision.md:193-197`), checklist item 9 (`:284`), and — normative constraint — non-goal §7 (`:303-306`): *"The similarity check is a self-check against the project's own sources and verbatim-quote hygiene, not a web-scale index."* This is **not a Turnitin replacement** and every user-facing surface must say so.
**Status:** Design ready — implementation plan in `2026-07-17-similarity-plan.md`.
**All paths repo-relative to the dothesis root.**

---

## 1. Problem and outcome

No plagiarism/similarity capability exists anywhere in the codebase. Re-verified by grep across `agent/`, `quality/`, `orchestrator/`, `engine/`, `skills/`: the only hits for `plagiar|similarit|shingl|winnow|fingerprint|n-gram` are title-similarity dedup for citations (`engine/utils/deduplicate_citations.py:100-194`), the literal word "plagiarism" in a retraction-keyword list (`engine/utils/citation_quality_filter.py:143`), and an ElevenLabs voice parameter (`engine/utils/elevenlabs.py:55`). None of these touch prose.

Students get their first similarity signal from Turnitin — after submission. LLM-drafted prose additionally risks verbatim overlap with the abstracts/claims the agent read in M2, and auto-drafted chapters risk copying each other (boilerplate duplication).

**Outcome:** a local, deterministic, offline self-check that (a) fingerprints draft chapters and the project's own source texts, (b) reports verbatim matched spans — chapter-vs-source and chapter-vs-chapter — with length, source, and location, (c) classifies each matched span for quote hygiene (quoted? cited?), and (d) surfaces everything as a **soft** rubric dimension plus a bounded pre-export report.

---

## 2. Inputs — what the check can actually see (grounded)

### 2.1 Draft prose (M5)

- State shapes: `m5_writing.final_sections` (list, the conversational/owned key — `agent/state.py:52`) or `m5_writing.chapters` (dict, auto-mode). The shipped rubric already tolerates both (`quality/rubric.py:15-19` `_sections`, `:22-23` `_all_prose`).
- Canonical chapter resolution: `chapters_from_final_sections` (`orchestrator/tools/m5_writing.py:1645-1678`) maps sections onto the six canonical chapters and **drops non-canonical sections — e.g. References** (`:1653-1655`). This is our first bibliography-noise firewall: resolve to canonical chapters and the reference list never enters fingerprinting.
- Stub filtering: `_is_stub_prose` (`orchestrator/tools/m5_writing.py:1722-1729`) — stub markers or <120 chars. Stub chapters are skipped (nothing to check).
- Precedent for shape-tolerant resolution inside a pure module: `agent/coherence.py:286-303` `_resolve_chapters` (lazy-imports `chapters_from_final_sections`, falls back to title lookup, never raises).

### 2.2 The project's own sources (M2) — the honest part

`literature_sources` is M2-owned state (`agent/state.py:38`). **No code path persists source abstracts today.** Verified across every writer:

| Writer | Shape persisted | Abstract? |
|---|---|---|
| `orchestrator/tools/m2_literature.py:218-233` (`scout_citations` mapping) | `{title, authors, year, source, url, doi}` | **No** |
| `agent/tools/research.py:85-100` (`_crossref_fallback`) | `{title, authors, year, venue, doi, url, verified}` | **No** (ironically filters on `has-abstract:true`, `:72`, then discards it) |
| `orchestrator/tools/domain_sources.py:108-118` (`norm_source`) | `{title, authors, year, venue, doi, url, verified}` | **No** |

The engine's `Citation` class *does* carry an `abstract` field (`engine/utils/citation_database.py:153,175,212-213`) and `agent_runner.py:1229-1232` writes abstracts into the scout's scratch markdown — but that text never reaches `literature_sources`. One partial exception: the M2 skill instructs the conversational agent to store *"title, authors, year, venue, DOI, abstract, 3–5 key claims (each with page ref …)"* per source (`skills/dothesis-m2-literature/SKILL.md:69-71`), so a skill-driven commit **may** carry `abstract` / `key_claims` keys — but nothing enforces it.

**Design consequence:** the source-overlap check reads, per source, an ordered list of optional text fields — `abstract`, `key_claims` (strings or dicts with a `quote`/`claim`/`text` key), `summary`, `title` — and degrades gracefully to title-only when that's all there is. The report must state its own coverage honestly (`sources_with_text` vs `sources_title_only`) so a "0 overlaps found" against 40 title-only sources is never read as a clean bill of health. **Follow-up (in the plan, Phase 6):** persist abstracts at the three mapping sites above — a one-line change each — which is what makes chapter-vs-source detection actually bite. Until then, the intra-thesis duplication check and quote hygiene around whatever text *is* held carry the near-term value.

### 2.3 Reused shipped patterns

- **Rubric dimension contract** (`quality/rubric.py`): `{name, weight, score, findings: [{issue, fix, chapter, severity}]}`, lazy imports so `import quality.rubric` stays light (`:27-31`), never crash — every dimension fails open (`coherence_dimension` `:430-452` is the model: try/except around the pure validator, `logger.exception`, empty findings on failure).
- **Roadmap #6 shared prose plumbing** (`agent/coherence.py`, per roadmap #11's "richer after 6 — shared prose-extraction," `roadmap.md:344`): reuse `segment_sentences` (`agent/coherence.py:62-67`) for citation-adjacency sentence bounds, `_nfc` NFC normalization (`:48-49`), the 160-char excerpt truncation convention (`:160,:278`), and the never-raise entry-point pattern (`:461-493`). `agent.coherence` is pure stdlib (its own header, `:11`), so importing it from `quality/` adds no heavy dependency; `quality` already reaches into `agent` (rubric `:54,:120,:143`).
- **Citation regex parity**: the inline-citation pattern is `_CITATION_REGEX = re.compile(r"\(([^)]+?),\s*(\d{4}|n\.d\.)\)")` (`orchestrator/tools/m5_writing.py:128`, used by `validate_citations_plain` `:131-155`). The pure similarity module must not import `orchestrator` (heavy: langchain), so it **duplicates this one-line regex locally** with a parity comment pointing at `m5_writing.py:128` and a parity test.

---

## 3. Placement

**Decision: a new pure module `quality/similarity.py`.** Rationale:

1. The roadmap literally scopes it there: *"Fingerprinting module in `quality/`"* (`roadmap.md:340`).
2. **Not thesis-stats**: this is product/pedagogy over *prose*; the thesis-stats submodule is the shared numeric engine vendored into dothesis + fillform, and fillform has no prose — a similarity module there would be dead weight in half its consumers.
3. **Not `agent/`**: the consumer is the quality gate (rubric dimension + export report), same layer as `quality/rubric.py`; `agent/coherence.py` lives in `agent/` because the M5 chat gate calls it inline — similarity has no chat-gate role (see §7, severity).

**Module contract** (mirrors `agent/coherence.py`'s header contract):
- Pure: stdlib only (`re`, `unicodedata`, `hashlib`), plus `from agent.coherence import segment_sentences` (itself pure stdlib). No LangChain, no I/O, no network, no clock, no `random`.
- The core API takes plain data (`chapters: dict[str, str]`, `sources: list[dict]`); only the entry point `check_similarity(context_store)` does shape-tolerant extraction (with the lazy `chapters_from_final_sections` import, mirroring `agent/coherence.py:292`).
- Entry points never raise.
- `quality/rubric.py` imports it lazily inside the new dimension function, per house convention (`quality/rubric.py:27-31`).

---

## 4. Algorithm — fingerprinting (normative; implement and unit-test exactly this)

### 4.1 Normalization + tokenization

Given raw prose, produce `tokens: list[Token]` where `Token = (text: str, start: int, end: int)` — `start`/`end` are character offsets **into the original string** so every reported span can quote and locate the original text.

1. **Noise stripping (offset-preserving — replace with spaces, never delete):**
   - `{{cite: label | title | url}}` grounding pills (`agent/runtime.py:359-364`). These embed the **full source title verbatim** in prose — the single biggest mechanical false-positive against `literature_sources` titles. Strip pattern: `\{\{cite:.*?\}\}` (non-greedy, DOTALL). Chat-surface prose may carry them into committed sections; stripping is cheap insurance either way.
   - Inline parenthetical citations matching the citation regex (§2.3) — "(Nguyen, 2023)" inside a span must not count as matched tokens, but its *position* is retained for the hygiene check (§6).
   - Reference-list-shaped lines *inside* a chapter (belt-and-braces on top of the canonical-chapter firewall §2.1): a line starting with an author-year bibliography pattern **and** containing a DOI/URL, or any line after a `References` / `Tài liệu tham khảo` heading (`orchestrator/tools/m5_writing.py:1633` `_REFERENCES_TITLE`) within the chapter body.
   - Markdown table rows and heading markers: lines whose letter-character ratio is < 0.5 (tables of numbers legitimately repeat between Results and Discussion and are the coherence gate's jurisdiction, not ours).
2. **Unicode NFC** (Vietnamese composed forms — same rationale as `agent/coherence.py:48-49`), then **lowercase**.
3. **Punctuation → spaces** (everything that is not a letter, digit, or combining mark; quotes and citation parens have already been recorded before this step for §6).
4. **Tokenize on whitespace.** No stemming, no diacritic stripping — stripping diacritics would conflate distinct Vietnamese words (e.g. *ma/mà/má/mã*) and manufacture false positives; NFC + exact match is the conservative choice.

### 4.2 Shingling

- **k = 7 tokens** per shingle. Rationale: Vietnamese (the product's default language) writes each syllable as a separate whitespace token, so 7 tokens ≈ 4–5 lexical words — inside the roadmap's 5–8 guidance and below typical quotation-policy thresholds; small enough that a "27-word span" (roadmap's own example, `roadmap.md:337`) yields ~21 overlapping shingles, large enough that formulaic academic connective phrases (≤ 5–6 tokens: "kết quả nghiên cứu cho thấy rằng", "trong bối cảnh nghiên cứu này") do not fingerprint on their own.
- Shingle *i* = tokens `[i, i+k)`, hashed as `blake2b(("\x1f".join(token_texts)).encode("utf-8"), digest_size=8)` → 64-bit int. **Never Python's builtin `hash()`** — it is salted per process (`PYTHONHASHSEED`) and would break determinism. blake2b-64 collisions are ~nil at thesis scale, and §4.4's token-level extension verifies every match anyway, so a collision can cost work but never a false report.

### 4.3 Winnowing (Schleimer, Wilkerson & Aiken 2003)

- **Window w = 4**: over every window of w consecutive shingle hashes, select the minimum hash; on ties, select the **rightmost** minimal hash (the paper's robust-winnowing tie rule — required for determinism and for the O(n) property that consecutive windows usually reselect the same fingerprint).
- Output: `fingerprints: list[(hash, shingle_index)]`, deduplicated on consecutive reselection.
- **Guarantee** (unit-test it): any verbatim match of length ≥ `t = w + k − 1 = 10 tokens` shares at least one selected fingerprint between the two texts; no match shorter than k tokens is ever detected. So detection floor = 10 tokens; reporting floors are higher (§5).
- Texts shorter than k tokens (most title-only sources in Vietnamese are longer; English titles may not be) fall back to a single shingle of all their tokens when `len(tokens) >= 5`, else they are skipped and counted in `sources_title_only` coverage.

### 4.4 Seed → extend → merge (exact spans, not hash matches)

1. Build a hash→positions index over each comparison target's fingerprints.
2. For each shared fingerprint hash, each (chapter_pos, target_pos) pair is a **seed**.
3. **Extend** each seed left and right by direct token-text comparison until mismatch → a maximal verbatim token run. This verifies the match (kills hash collisions) and gives exact boundaries; report boundaries in original-character offsets via the Token offsets.
4. **Merge** overlapping/adjacent runs (gap ≤ 2 tokens) per (chapter, target) pair.
5. **Bound the work:** cap seeds per (chapter, target) pair at 500, taken in document order, and set `truncated: true` on the report if hit. Pathological inputs (a chapter that *is* the source) stay O(n).

Everything above is deterministic: same input bytes → same output, independent of process, platform, and hash seed.

---

## 5. Comparisons and thresholds

| Comparison | Corpus | Min reported span | Finding check id |
|---|---|---|---|
| (a) Chapter vs each source text (§2.2 fields) | per-source | **12 tokens** | `similarity.source_overlap` |
| (b) Chapter vs chapter (all 15 pairs of the 6 canonical chapters) | intra-thesis | **20 tokens** | `similarity.intra_duplication` |

- 12 tokens (~8–9 Vietnamese lexical words) sits above the 10-token detection floor and below the roadmap's exemplar 27-word span; it is long enough that shared domain terminology alone can't reach it.
- 20 tokens for intra-thesis because chapters legitimately share hypothesis statements, construct definitions, and section boilerplate at moderate length; only sustained copy-paste should surface. Spans that consist of a repeated *hypothesis statement* (the exact `H1: …` text from M3, which Results and Discussion both legitimately restate) are additionally exempted by checking the span text against `m3_design.hypotheses` statements.
- **No headline similarity percentage.** Recommendation (final): do **not** report "12% similarity". A corpus of the project's own handful of sources cannot produce a number commensurable with Turnitin's web-scale index; printing one invites exactly the misreading vision §7 forbids (a student seeing "3%" and believing they're Turnitin-safe). Report **counts and spans only**: "N verbatim spans totalling M words" per chapter / per source. The report schema (§8) carries `headline: null` deliberately, with a comment forbidding a percentage.

---

## 6. Quote hygiene

For each reported **source-overlap** span, classify:

- **quoted**: the span lies entirely inside a quotation region — between matching double quotes (`"…"`, `“…”`, `«…»`) or on markdown blockquote (`>`) lines. Quote regions are computed on the *original* text before punctuation stripping.
- **cited**: an inline citation (the §2.3 regex) occurs within the same sentence as the span (sentence bounds via `segment_sentences`, `agent/coherence.py:62-67`) or within 200 characters after the span's end. Bonus precision, not a gate: if the citation's `(author, year)` matches the matched source's first-author surname + year (parity with `_ref_citation_key`, `orchestrator/tools/m5_writing.py:120-123`), set `cited_to_source: true`.

| quoted | cited | Result |
|---|---|---|
| yes | yes | clean — **no finding** |
| yes | no | finding: *"This 27-word quoted span matches Nguyen 2023 but has no citation — cite it with a page number."* |
| no | yes | finding: *"This 27-word span matches Nguyen 2023 verbatim and is cited but not quoted — put it in quotation marks with a page number, or paraphrase."* |
| no | no | finding: *"This 27-word span matches Nguyen 2023 — quote it with a page number, or paraphrase."* |

Intra-thesis spans get: *"This 33-word span in Discussion duplicates Results verbatim — consolidate or rewrite; chapters should not repeat each other."* (No quote-hygiene classification for intra spans — quoting yourself is not the fix.)

Finding dicts use the rubric shape (`issue`, `fix`, `chapter`, `severity`) with the span excerpt (≤ 160 chars, `agent/coherence.py` convention) embedded in `issue`.

---

## 7. Severity: everything soft — reconciled with the #1 bar

Initiative #1's bar, restated in the coherence module we're building beside: **"only provably-wrong blocks"** (`agent/coherence.py:5-8` — its single hard check is a prose number contradicting a persisted result). A similarity match does not clear that bar:

- A verbatim match is **evidence of overlap, not proof of misconduct** — the span may be a properly attributed idea our quote detector misread, a fixed technical phrase, a definition both texts quote from a third party, or (title-only corpus) the student legitimately naming a paper.
- The tool is a **self-check, not an adjudicator** (vision §7, `vision.md:303-306`). Its job is to warn the student before Turnitin does, never to block their export on an accusation.

Therefore: **every finding this initiative emits is `severity: "soft"`.** Nothing enters `blocking` (`quality/rubric.py:490` collects only hard findings). Enforce with a test, not a comment (precedent: the coherence plan's hard-severity whitelist test). Export proceeds; the report is attached, advisory.

Dimension scoring (bounded, precedent `source_verification_dimension`, `quality/rubric.py:425-427`): weight **0.10**; `score = max(0.0, 1 − 0.10·(source-overlap findings) − 0.05·(intra-duplication findings))`, computed over the **capped** findings list (≤ 15 findings surfaced; counts in `meta` carry the true totals).

---

## 8. Output surfaces

### 8.1 Rubric dimension

`similarity_dimension(context_store) -> dict` in `quality/rubric.py`, wired into `score_thesis` (`quality/rubric.py:455-495`) after `coherence_dimension`. Lazy import of `quality.similarity`, try/except fail-open, shape per §2.3. Reaches users through the existing `review_thesis` tool (`agent/tools/writing.py:293-318`) with zero extra wiring.

### 8.2 Pre-export report (bounded — never dump full text)

`similarity_report(context_store) -> dict` (same module, built from the same single `check_similarity` pass):

```json
{
  "counts": {"source_overlap_spans": 0, "intra_dup_spans": 0, "hygiene_findings": 0,
              "sources_with_text": 0, "sources_title_only": 0, "chapters_checked": 0},
  "top_spans": [ {"kind": "source|intra", "chapter": "results", "source": "Nguyen 2023",
                   "tokens": 27, "excerpt": "≤160 chars", "quoted": false, "cited": false} ],
  "per_source": [ {"label": "Nguyen 2023", "spans": 2, "matched_tokens": 41} ],
  "per_chapter_pair": [ {"a": "results", "b": "discussion", "spans": 1, "matched_tokens": 33} ],
  "coverage_note": "Checked against N sources with stored text; M sources are title-only — this is a self-check against the project's own sources, not a Turnitin scan.",
  "truncated": false,
  "headline": null
}
```

Bounds: `top_spans` ≤ 10 (sorted by token length desc, then chapter/offset for determinism), `per_source` ≤ 20, excerpts ≤ 160 chars. The `coverage_note` **always** carries the not-Turnitin disclaimer.

Surfacing: `export_docx` (`agent/tools/writing.py:36` factory) attaches the report under a `similarity` key in its returned JSON — advisory, never a gate — which is what the web run drawer renders from (roadmap `:341-342` "export-time report in the run drawer"; the drawer's client rendering is a web follow-up outside this initiative's Python scope). `review_thesis` already returns the dimension with findings.

### 8.3 M5 skill copy

`skills/dothesis-m5-writing/SKILL.md` (193 lines; already documents the coherence gate at `:138`) gains a short paraphrase-hygiene section: never reproduce source sentences verbatim while drafting; quote + cite with page number when exact wording matters; the similarity self-check runs at review/export and flags unquoted verbatim spans; it is a self-check, not Turnitin.

---

## 9. Performance

Budget: a thesis is ~50–100k words (~130k Vietnamese tokens) × ~50 sources (mostly short texts) + 15 chapter pairs.

- Tokenize + shingle + winnow: one pass per text, O(n) — done **once** per text, reused across all comparisons.
- Matching: dict lookups over fingerprint indexes (winnowing keeps ~2/(w+1) of shingles ≈ 40%); extension is linear in matched length; the 500-seed cap (§4.4) bounds adversarial cases.
- Target: full check < 2 s pure Python on a 100k-word thesis; CI smoke test asserts < 10 s on a synthetic 200k-token input (generous for slow runners).
- Memory: fingerprint lists of ints + token offset arrays — a few MB; nothing quadratic is ever materialized.

---

## 10. Vietnamese handling

The product's default language (`M5_CHAPTER_TITLES_VI`, `orchestrator/tools/m5_writing.py:1625-1633`; bilingual keyword lists throughout `agent/coherence.py:82-87`). Decisions: NFC + whitespace tokenization only (§4.1); diacritics preserved; k chosen for syllable-per-token counts (§4.2); quote characters include `«»` and curly quotes; the citation regex is script-agnostic (`[^)]+?` author group). Test fixtures must include Vietnamese prose with composed and decomposed input encodings normalizing to the same fingerprints.

---

## 11. Testing strategy (all offline — see plan for phase mapping)

1. **Known-plant:** a 30-word span copied from a source `abstract` into a chapter → detected, exact span text + source label + chapter reported.
2. **Hygiene pass:** the same span wrapped in `“…”` with `(Nguyen, 2023)` in-sentence → no finding.
3. **Paraphrase:** a genuine paraphrase (same ideas, different wording) → no finding.
4. **Intra-thesis:** a 25-token paragraph duplicated Results→Discussion → `similarity.intra_duplication`; a shared M3 hypothesis statement → exempt, no finding.
5. **Bibliography immunity:** a References `final_section` and in-chapter reference-shaped lines → zero findings; `{{cite:}}` pills containing full source titles → zero findings.
6. **Determinism:** two runs → byte-identical results; subprocess runs under different `PYTHONHASHSEED` values → identical fingerprints.
7. **Winnowing property:** randomized (seeded) texts with a planted common substring of exactly t = 10 tokens always share ≥ 1 fingerprint.
8. **Never-crash:** `None`s, empty stores, string `analysis_results`-style garbage, non-dict sources → empty report, no exception.
9. **Soft-only:** no finding from this module ever carries `severity: "hard"`; `score_thesis(...)["blocking"]` unaffected.
10. **Performance smoke:** §9 bound.

---

## 12. Summary of design decisions

| Decision | Choice | Why |
|---|---|---|
| Placement | `quality/similarity.py`, pure | Roadmap `:340`; product/pedagogy over prose; fillform has no prose |
| Algorithm | k=7 shingles, blake2b-64, winnow w=4, seed→extend→merge | Deterministic, O(n), exact verified spans, 10-token detection floor |
| Normalization | NFC + lowercase + punctuation→space + whitespace tokens; keep diacritics | Vietnamese-first; conservative w.r.t. false positives |
| Bibliography noise | Canonical-chapter resolution drops References; strip cite-pills, citation parens, ref-shaped lines, table rows | #1 noise source killed at three layers |
| Thresholds | Report ≥ 12 tokens (source), ≥ 20 (intra); hypothesis statements exempt intra | Above detection floor, below the 27-word exemplar |
| Headline number | **None** — counts and spans only, `headline: null` | A fake "12%" invites Turnitin misreading (vision §7) |
| Severity | All soft, never blocks | #1 bar: only provably-wrong blocks; match = evidence, not proof; self-check, not adjudicator |
| Abstracts | Not persisted today (verified §2.2); design reads optional fields, reports coverage; follow-up persists them | Honesty over pretending; intra-dup + hygiene deliver value on day one |
