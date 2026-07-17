# M5 Renderer over Verified State — Implementation Plan

**Date:** 2026-07-18
**Design:** `2026-07-18-m5-renderer-design.md` (normative — read it first)
**Executor:** Opus agent, TDD throughout (`superpowers:test-driven-development`):
every task writes the failing test FIRST, then the minimal implementation,
then refactor. Pure renderers + fixture tests land before any compose/export
integration; skill copy lands last.

Conventions for every task below:

- **Files** are exact paths from repo root `/Users/caonguyenvan/project/dothesis`.
- **Verify** commands run offline (no network, no LLM). Root suite uses
  `pytest.ini`; orchestrator tests run from their own tree.
- **Done-when** is the acceptance check — do not move on until it holds.
- Hard constraints from the design, restated: renderers are **stdlib-only,
  no LLM calls, fail-open** (§4); `results_render.py` must NOT import
  `m5_writing`, `boto3`, or `langchain` (§3); rendered numbers are **verbatim
  from state** (§4.1); nothing added may block a compose/export (§9).

---

## Phase 1 — Pure renderer module + golden-fixture tests

### Task 1.1 — Fixtures + family detection

**Files:**
- `tests/fixtures/renderer_blocks.py` (new) — plain-dict fixtures, no I/O:
  - `PLS_BLOCK`: the M4 skill's canonical example **verbatim**
    (`skills/dothesis-m4-analysis/SKILL.md:165-185` — descriptives,
    measurement_model with LS/PI, HTMT matrix, one hypothesis_test r-H1,
    structural_model with r2/q2).
  - `CBSEM_BLOCK`: same measurement shape + `structural_model` carrying
    `r2` and `cfi/tli/rmsea/srmr/chi2_df` (keys per
    `agent/stats_validation.py:305-308`), plus a variant carrying the op-payload
    `fit` sub-dict (`docs/superpowers/specs/2026-07-17-cb-sem-design.md` §6.2)
    and paths with `se`/`z`/`p`.
  - `REGRESSION_BLOCK`: hypothesis_tests + `structural_model.r2` only.
  - `SCREENING_BLOCK`: the data-screening design §8.2 example verbatim
    (`2026-07-17-data-screening-design.md:497-510`), narrative included.
  - `FREE_TEXT_BLOCK` (a string), `LEGACY_STEP_BLOCK`
    (`{"results": {"step1": {...}}}`, per `agent/stats_validation.py:224-229`),
    `PARTIAL_BLOCK` (measurement_model only), `MALFORMED_BLOCK`
    (non-dict rows, string loadings).
- `tests/test_results_render_family.py` (new)
- `orchestrator/tools/results_render.py` (new) — implement only
  `detect_family` in this task.

**Tests to write first:** PLS→`"pls_sem"`, CB-SEM (both fit placements)→
`"cb_sem"`, regression→`"regression"`, free-text/legacy/None→`None`;
methodology-string tiebreaker (`"CB-SEM (AMOS)"` breaks a measurement-only
block toward `cb_sem`, mirroring `quality/rubric.py:522-529`); never raises on
garbage input.

**Verify:** `python -m pytest tests/test_results_render_family.py -q`

**Done-when:** all pass; `python -c "import ast,sys; t=ast.parse(open('orchestrator/tools/results_render.py').read()); print([n.names[0].name for n in ast.walk(t) if isinstance(n,ast.Import)])"`
shows stdlib modules only (no boto3/langchain/m5_writing/pandas/numpy).

### Task 1.2 — Results-table renderers (golden markdown)

**Files:** `orchestrator/tools/results_render.py`,
`tests/test_results_render_tables.py` (new).

Implement `render_results_tables(block, language)` per design §4.2–§4.4:
kinds `descriptives`, `measurement_model`, `discriminant_validity`,
`model_fit` (cb_sem only), `structural_paths`, `r2_q2` (pls only for Q²);
sentinel wrapping `<!--dt-rendered:begin kind=… sha=…-->` /
`<!--dt-rendered:end kind=…-->`; sha = sha256[:12] of
`json.dumps(source_subblock, sort_keys=True, ensure_ascii=False, default=str)`
(the `agent/provenance.py` `_sha12` recipe); number formatting per §4.1
(floats `:.4f` trimmed, ints raw, `p` strings like `"<0.001"` verbatim,
missing cell `—`); vi/en header maps (`M5_CHAPTER_TITLES_VI` precedent,
`orchestrator/tools/m5_writing.py:1625-1632`); duplicate hypothesis ids keep
the last entry (registry superseded logic, `agent/coherence.py:227-248`).

**Tests to write first:**
- `PLS_BLOCK` → assert the **exact expected markdown string** for each block
  (byte-for-byte, sentinels included) — the numbers 0.81/0.86/0.90/0.62/0.42/
  0.34/7.01/`<0.001`/0.18/0.56/0.31 from the fixture appear verbatim; no
  CFI/TLI/RMSEA anywhere (family purity, `SKILL.md:187-193`).
- `CBSEM_BLOCK` → exact fit table with Hu & Bentler threshold column
  (`SKILL.md:68-69`); no HTMT/Q² kinds emitted unless present; `se`/`z`
  columns render when `t` absent.
- `REGRESSION_BLOCK` → exact coefficient + model-summary tables.
- Determinism: two calls on `copy.deepcopy` inputs and on key-order-shuffled
  dicts → identical bytes.
- Fail-open: `PARTIAL_BLOCK` → only measurement table; `MALFORMED_BLOCK` →
  bad rows skipped/`—` cells, no raise; `FREE_TEXT_BLOCK`/`LEGACY_STEP_BLOCK`/
  `None` → `[]`.
- No derived numbers: assert output contains no value absent from the fixture.

**Verify:** `python -m pytest tests/test_results_render_tables.py -q`

**Done-when:** golden strings pinned in the test file pass; determinism and
fail-open cases green.

### Task 1.3 — Cleaning-section renderer

**Files:** `orchestrator/tools/results_render.py`,
`tests/test_results_render_cleaning.py` (new).

Implement `render_cleaning_section(block, language)` per design §7.2:
`data_screening.narrative` **verbatim** + screening-summary table
(Stage/removed/n) from fields present; kind `data_cleaning`; `None` when the
sub-block is absent.

**Tests first:** `SCREENING_BLOCK` → exact expected markdown; assert
`SCREENING_BLOCK["data_screening"]["narrative"] in out["markdown"]`
(character-identical — the design-§8.2 rule "numbers never re-typed",
`2026-07-17-data-screening-design.md:538-541`); narrative-only fixture →
paragraph without table; no `data_screening` → `None`; determinism.

**Verify:** `python -m pytest tests/test_results_render_cleaning.py -q`

**Done-when:** verbatim-narrative assertion passes; fail-open green.

### Task 1.4 — Limitations renderer

**Files:** `orchestrator/tools/results_render.py`,
`tests/test_results_render_limitations.py` (new),
`tests/fixtures/renderer_blocks.py` (extend with `NESTED_CS_WEAK`: nested
store carrying `m3_design.sample_plan.power_analysis{recommended_n:200,
justification:"…"}`, `m4_analysis.analysis_results` with descriptives n=140,
HTMT 0.87 pair, one `decision:"not supported"` hypothesis, screening removals;
and `NESTED_CS_CLEAN` with no weaknesses).

Implement `render_limitations(nested_cs, rubric_findings=None, language)` per
design §7.3: sources exactly as tabled (power reads mirror
`agent/viva.py:208-217, 166-175`; cutoffs from `SKILL.md:203-205`; soft
findings via lazy fail-open import of
`agent.stats_validation.validate_analysis_results`; `rubric_findings` consumed
only when passed). Cap 8, hard-first. Kind `limitations`. `None` on zero
weaknesses.

Note: the soft-findings source imports `agent.stats_validation` **lazily
inside a try/except** — the module stays importable stdlib-only; the test for
this path may run with the real module (it is pure) and must also pass when
the import is monkeypatched to raise (fail-open).

**Tests first:** `NESTED_CS_WEAK` → exact expected bullets (power bullet
contains "n=140" and "N=200" and the justification string; HTMT bullet
contains "0.87"; screening bullet contains the removal counts; not-supported
bullet names the hypothesis id with its β/p verbatim); `NESTED_CS_CLEAN` →
`None` (no boilerplate humility); disclose-and-frame register asserted (each
bullet contains no blame words, contains a framing clause — assert on the
fixed templates); `rubric_findings` passed → extra capped bullets; determinism;
fail-open on missing m3/m4.

**Verify:** `python -m pytest tests/test_results_render_limitations.py -q`

**Done-when:** exact bullets pinned and passing; clean-state → `None`.

## Phase 2 — Weave / strip / verify primitives

### Task 2.1 — `weave`, `strip_rendered_blocks`, `rendered_kinds`, `verify_rendered_blocks`

**Files:** `orchestrator/tools/results_render.py`,
`tests/test_results_render_weave.py` (new).

Implement per design §5 (weave rules 1–4) and §6:
- token syntax `[[DT:<kind>]]` on its own line → replaced by the block;
- missing token → block appended at chapter end;
- duplicate tokens / already-woven kinds → deduped (idempotent);
- results-chapter-only drop of unmarked majority-numeric pipe tables when ≥1
  block woven (`drop_llm_tables=True` flag the caller sets only for the
  results chapter);
- `strip_rendered_blocks` removes sentinel-delimited spans (tolerant of
  whitespace, returns input unchanged on unbalanced sentinels);
- `verify_rendered_blocks(prose, block)` re-renders and compares shas →
  list of mismatch findings dicts (soft), `[]` on no sentinels/no block.

**Tests first:** token replacement exact; append fallback; idempotency
(`weave(weave(p, b), b) == weave(p, b)`); numeric-table drop (LLM table with
β/t/p cells removed; text-heavy qual table kept; nothing dropped when no
blocks woven or flag false); strip round-trip
(`strip_rendered_blocks(weave(prose, blocks)) == `prose-with-tokens-removed
modulo whitespace); unbalanced sentinel → unchanged input; verify: clean →
`[]`, hand-edited cell → one mismatch finding; all functions never raise on
garbage.

**Verify:** `python -m pytest tests/test_results_render_weave.py -q`

**Done-when:** idempotency + round-trip properties green.

### Task 2.2 — Export-pipeline survivability regression test

**Files:** `tests/test_results_render_pipeline.py` (new). No production code
expected (this pins design §4.4's survivability claims; fix
`results_render.py` if any claim fails, never the sanitizers).

**Tests first:** for a woven results section:
- `orchestrator.tools.m5_writing._sections_to_markdown([{title, prose}])`
  output still contains the intact table rows and both sentinels
  (`m5_writing.py:247-292` chain: `_scrub_internal_markers`,
  `_split_run_on_hypotheses`, `_mermaid_to_prose`,
  `_normalize_prose_markdown`, dash normalization);
- `orchestrator.tools.m5_writing.sanitize_prose(prose)` leaves the rendered
  table untouched (`_drop_placeholder_tables` no-fire on `—`/`-` cells,
  `m5_writing.py:2437-2479`);
- a rendered table row `| H1 | LS -> PI | …` is not split by
  `_split_run_on_hypotheses` (colon-guard, `m5_writing.py:351-379`).

Note: importing `m5_writing` pulls boto3/langchain — these are already test
deps of the repo (`orchestrator/tests/test_agents_m5.py` imports it); mark
the module `pytestmark = pytest.mark.filterwarnings(...)` only if needed.

**Verify:** `python -m pytest tests/test_results_render_pipeline.py -q`

**Done-when:** all survivability pins green.

## Phase 3 — Checker integration (authoritative-not-suspect)

### Task 3.1 — Coherence strips rendered blocks + the gate-proof test

**Files:** `agent/coherence.py` (edit `_resolve_chapters`, `:286-303`: pipe
each resolved chapter string through a lazy fail-open
`strip_rendered_blocks`), `tests/test_coherence_rendered_blocks.py` (new).

**Tests first (the design-§10 proof):**
1. Build `final_sections` where the results chapter =
   `weave(narrative_prose, render_results_tables(PLS_BLOCK))` with narrative
   quoting the correct β=0.34/p<0.001, and a discussion chapter consistent
   with the decision. `validate_m5_sections(final_sections, flat_context)`
   (`agent/coherence.py:463-475`) → `passed=True`, zero hard findings — **a
   rendered table never trips prose≠numbers**.
2. Same sections but the narrative (outside sentinels) says "β = 0.55" →
   exactly the hard `coherence.number_mismatch` fires
   (`coherence.py:354-384`) — the gate still has teeth around rendered blocks.
3. A hand-tampered table cell inside sentinels (0.34→0.43) with correct
   narrative → still zero hard findings from coherence (stripped), but
   `verify_rendered_blocks` from Task 2.1 reports the sha mismatch — document
   in the test that tamper-detection is verify's job, not coherence's.
4. `strip_rendered_blocks` import failure (monkeypatch to raise) →
   `validate_m5_sections` still returns (fail-open, `crashed` not set by this).

**Verify:** `python -m pytest tests/test_coherence_rendered_blocks.py tests/test_coherence_dimension.py -q`
(the second file guards no regression in the existing rubric dimension).

**Done-when:** proof tests 1–2 green; existing coherence tests untouched-green.

### Task 3.2 — Similarity strips rendered blocks

**Files:** `quality/similarity.py` (edit `_resolve_chapters`, `:221-236`:
same lazy fail-open strip), `tests/test_similarity_rendered_blocks.py` (new).

**Tests first:** methodology chapter carrying the rendered cleaning block and
results chapter carrying rendered tables (shared n/values) →
`check_similarity` intra-thesis findings do not reference sentinel content;
existing `tests/test_similarity.py` stays green; strip failure → fail-open.

**Verify:** `python -m pytest tests/test_similarity_rendered_blocks.py tests/test_similarity.py -q`

**Done-when:** both files green.

## Phase 4 — Compose integration (auto-mode + partner + chat full-draft)

### Task 4.1 — `compose_chapter` weaves; prompts get tokens

**Files:**
- `orchestrator/tools/m5_writing.py` — in `compose_chapter`
  (`:2490-2584`): for `chapter_name in ("results", "methodology",
  "conclusion", "discussion")`, build blocks from `context_slice`
  (results→`render_results_tables(context_slice.get("results") or
  context_slice.get("analysis_results"))`; methodology→
  `render_cleaning_section`; conclusion/discussion→`render_limitations` over
  the reconstructed nested slice), pass each block's markdown into the prompt
  kwargs as a new `{rendered_blocks}` key, and apply
  `weave(prose, blocks, drop_llm_tables=(chapter_name=="results"))` **after**
  `sanitize_prose` (`:2572`). All wrapped fail-open (blocks build failure →
  compose exactly as today).
- `orchestrator/prompts/m5/results.md` — replace the three "Present a
  Markdown table" instructions (`:53-66`) with token-placement instructions
  (`[[DT:measurement_model]]`, `[[DT:discriminant_validity]]`,
  `[[DT:structural_paths]]`, `[[DT:model_fit]]`, `[[DT:descriptives]]`,
  `[[DT:r2_q2]]`) + "never emit a statistics table yourself"; keep the
  `[overview] → [table] → [interpretation]` pattern (`:92-96`) but around
  tokens.
- `orchestrator/prompts/m5/methodology.md` — add `[[DT:data_cleaning]]`
  guidance for the data-collection/screening passage.
- `orchestrator/prompts/m5/conclusion.md` and `discussion.md` — add
  `[[DT:limitations]]` guidance for the limitations passage.
- `orchestrator/tests/test_m5_compose_render.py` (new).

**Tests first (mock the LLM — monkeypatch `m5_writing._get_llm` to return
canned prose containing/omitting tokens, the `test_agents_m5.py` pattern):**
- LLM emits tokens → composed prose has tables at token positions, numbers
  verbatim from the fixture block;
- LLM omits tokens → tables appended, chapter still complete;
- LLM emits its own β/t/p table → dropped, rendered table present;
- empty `analysis_results` → prose identical to pre-change behavior
  (byte-compare against a no-renderer compose with the same mocked LLM);
- non-affected chapters (intro/lit_review) → zero renderer involvement;
- `compose_all_sections` (`m5_writing.py:1805-1877`) and
  `compose_export.compose_sections` (`compose_export.py:61-174`) end-to-end
  with mocked LLM → results section carries sentinels (proves both callers
  inherit via `compose_chapter`).

**Verify:** `cd orchestrator && python -m pytest tests/test_m5_compose_render.py tests/test_agents_m5.py -q`

**Done-when:** all green including the existing `test_agents_m5.py`.

## Phase 5 — Export-time safety net

### Task 5.1 — `run_export(context_store=…)` + `ensure_rendered`

**Files:**
- `orchestrator/tools/results_render.py` — `ensure_rendered(sections,
  nested_cs, language)` : for sections whose title maps to
  results/methodology/conclusion (reuse the `chapters_from_final_sections`
  title reverse-lookup, `m5_writing.py:1645-1678`), weave only kinds missing
  per `rendered_kinds`; pure, fail-open, idempotent.
- `orchestrator/tools/m5_writing.py` — `run_export` (`:2127-2157`) gains
  `context_store: dict | None = None`; when set, sections =
  `ensure_rendered(sections, context_store, language)` before the
  citeproc/plain branch. Default `None` → byte-identical current behavior.
- Callers pass their store:
  - `agent/tools/writing.py:251` (full export; `full_cs` already loaded
    `:107-111`) — and the module-scoped path `:161-166` does NOT pass it
    (module exports are not the 6-chapter thesis);
  - `api/app/agent_state.py:281` (auto-export hook; it has the nested store);
  - `api/app/routers/m5_editor.py:576`;
  - `orchestrator/tools/compose_export.py:194` (`compose_and_export` already
    holds `context_store`).
- `tests/test_run_export_render.py` (new; monkeypatch
  `_export_docx_via_engine`/`compile_pdf`/S3 per the existing
  `orchestrator/tests/test_agents_m5.py:130-161` pattern, or assert on the
  sections handed to a mocked `_run_export_citeproc`).

**Tests first:** sections without sentinels + `context_store` → exporter
receives woven sections; sections already woven → unchanged (idempotent);
`context_store=None` → unchanged; `ensure_rendered` raising (monkeypatched)
→ export still succeeds with original sections; caller signature updates
covered by one test per caller where cheap (agent tool test with a stub store
following `agent/tests` conventions if present, else the orchestrator test
asserts the kwarg plumbing).

**Verify:** `python -m pytest tests/test_run_export_render.py -q && cd orchestrator && python -m pytest tests/test_agents_m5.py -q`

**Done-when:** green; a grep confirms every `run_export(` call site either
passes `context_store` or is the module-scoped/partner-internal path with a
comment saying why not.

## Phase 6 — Chat tool + skill copy (last, per "skills first" the copy PR is reviewable standalone)

### Task 6.1 — `render_verified_sections` chat tool

**Files:** `agent/tools/writing.py` (add a third factory tool alongside
`export_docx`/`review_thesis`, `:25-351`):
`render_verified_sections(kind: str)` → for `"results_tables" |
"data_cleaning" | "limitations"`, load the nested store
(`store.load_full_context_store()`, the `:107-111` pattern), call the matching
renderer, return `{"ok": True, "markdown": …, "kinds": […]}` or
`{"ok": False, "reason": "no_data"}` — read-only, no commit, no LLM.
Register it wherever `make_writing_tools` is consumed (same return list).
**Files:** `tests/test_render_tool.py` (new, stub store).

**Tests first:** stub store with `PLS_BLOCK` → markdown equals the pure
renderer's output exactly; empty store → `no_data`; store raising →
`no_data`-style error JSON, no exception.

**Verify:** `python -m pytest tests/test_render_tool.py -q`

**Done-when:** tool output byte-equals pure renderer output.

### Task 6.2 — Skill copy: M5 (and one M4 pointer)

**Files:** `skills/dothesis-m5-writing/SKILL.md`:
- Quality bars (`:133-148`): replace "copy, never retype" for Results
  (`:137-138`) with: Tables 4.1–4.3 / fit come from
  `render_verified_sections("results_tables")` — include the returned
  markdown **verbatim, sentinels included**; you write only the overview and
  interpretation prose around each table; never hand-build a statistics
  table.
- Chapter 3: the data-cleaning passage = `render_verified_sections("data_cleaning")`
  verbatim (supersedes narrating `data_screening.narrative` by hand — the
  data-screening design's M5 rule, now tool-enforced).
- Limitations bar (`:148`): seed from `render_verified_sections("limitations")`;
  discuss each bullet, delete none silently; if it returns `no_data`, write
  honest limitations from state as today.
- Note under the coherence bullet (`:138-142`): rendered blocks are
  authoritative — the gate checks your narrative against the same state the
  tables rendered from.

`skills/dothesis-m4-analysis/SKILL.md`: one sentence in the structured-blocks
section (`:158-163`): "these blocks are rendered verbatim into Chapter 4 by
M5 — completeness here IS the chapter" (no behavioral change).

**Verify:** `python -m pytest tests/ -q` (skill files are content; full root
suite guards nothing regressed) and a manual read-through against
`AGENTS.md`'s skills-first contract.

**Done-when:** copy merged; no test regressions.

### Task 6.3 — Full-suite sweep + determinism audit

**Verify:**
```
python -m pytest tests/ -q
cd orchestrator && python -m pytest tests/ -q
python -m pytest tests/test_results_render_tables.py -q --count=2  # if pytest-repeat present; else run twice
```
plus the import-purity check from Task 1.1 repeated.

**Done-when:** both suites green; renderer module still stdlib-only; running
the golden-table tests twice yields identical results (no hidden state).

---

## Explicit out-of-scope (do not implement)

- Rendering the orchestrator legacy `{results:{step:…}}` shape (design §2
  non-goal — a follow-on adapter can reuse `claims_from_table` precedent).
- Certificate/rubric wiring of `verify_rendered_blocks` beyond the function
  itself (roadmap #12 follow-on; the function + tests ship now).
- Any web/editor UI change (the editor consumes the same
  `final_sections`/export routes untouched).
- Any change to M4 persistence, `commit_slice` gates, or the coherence
  check catalogue beyond the strip in Task 3.1.
