# Hypothesis Registry + Cross-Chapter Coherence Gate — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-coherence-gate-design.md` (read it first — the registry shape §4.2, check catalogue §5, extraction rules §6, and integration contracts §7 are all normative there; this plan only sequences them)
**Executor notes:** All paths relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–3 are pure functions with zero wiring and land before anything touches shipped code. Phase 4 is the only task that edits initiative #1's shipped module — its regression suite must be green in the same task. No thesis-stats submodule changes anywhere in this plan.

**Hard constraints (from the design):**
- Only `coherence.number_mismatch` (NU1) may ever carry `severity: "hard"`. Enforce with a test (Task 3.4), not a comment.
- Everything in `agent/coherence.py` is pure: stdlib `re`/`unicodedata` only; no LangChain, no `thesis_stats` import, no I/O, no clock.
- Entry points (`validate_m5_sections`, `validate_coherence`) never raise.

---

## Phase 1 — the pure registry (`agent/coherence.py`)

### Task 1.1 — Scaffold: id normalization + finding/aggregate helpers
- **Files:** `agent/coherence.py` (new), `agent/tests/test_coherence_registry.py` (new)
- Tests first: `normalize_hypothesis_id` over the shapes in design §4.2 —
  `"H1"`, `"h1"`, `"r-H1"`, `"H12"`, `"H1: LS has a positive effect on PI"`,
  `"Giả thuyết H2"`, `"Hypothesis 3"` → `"H1"/"H1"/"H1"/"H12"/"H1"/"H2"/"H3"`;
  dict inputs (`{"id": "H1"}`, `{"label": "H2"}`, `{"statement": "H3: …"}`);
  garbage (`None`, `{}`, `"the moderating role"`) → `None`.
- Implement: `normalize_hypothesis_id`, a local `_finding(check, severity,
  message, *, hypothesis=None, chapter=None, observed=None, expected=None,
  tolerance=None, source="prose")` helper emitting the #1 §5 dict shape
  (location keys `table/construct/item/path` present-and-null plus the extra
  `hypothesis`/`chapter` keys — design §6.5), and reuse of the aggregate
  shape from `agent/stats_validation.py:43-48` (copy `_agg` locally or import
  it — importing is fine, `agent.stats_validation` is pure; decide once,
  document in a comment).
- **Verify:** `python -m pytest agent/tests/test_coherence_registry.py -q`
- **Done when:** green; `import agent.coherence` succeeds with no
  langchain/thesis_stats/network imports (assert in a test via
  `sys.modules` inspection after a fresh subprocess import, or simply by
  keeping the module import-light and eyeballing — the subprocess check is
  preferred and cheap).

### Task 1.2 — `build_registry`
- **Files:** same two files.
- Tests first, driven by the real shapes cited in design §4.2:
  - M3 `hypotheses` as strings (M3 skill shape) and as dicts
    (`orchestrator/schemas/m3.py:47`); `conceptual_model` with `nodes[].{id,label}` +
    `edges[].{id: "H1", source, target, hypothesis, effect_type}`
    (`orchestrator/agents/m3_design.py:502-542`).
  - M4 `analysis_results` = the M4 skill's canonical sample block
    (`skills/dothesis-m4-analysis/SKILL.md:132-151`) — assert `m4.decision_supported`,
    `significant` (from `"<0.001"` via the `_p_value` semantics —
    reuse/port `agent/stats_validation.py:31-40`), `numbers` normalized,
    `path` arrow-normalized (`"LS → PI"` → `"LS -> PI"`).
  - Direction resolution order: matching edge `effect_type` wins over
    statement wording; `effect_type: "moderates"` → `direction=None`;
    no edge + statement "has a negative effect" → `("negative", "statement_wording")`;
    neither → `None`.
  - Duplicate `hypothesis_tests` entries for one id → last entry feeds
    `m4.numbers`, `superseded_count == 1`; an entry with an id in neither M3
    list nor edges → a registry row with `in_m3 == False` (the CO2 input).
  - M5 side: `chapters` dict and `final_sections` list both resolve via
    `chapters_from_final_sections` semantics (lazy-import
    `orchestrator.tools.m5_writing.chapters_from_final_sections` — the
    precedent for agent→orchestrator lazy imports is
    `agent/tools/state_tools.py:91`); only results/discussion/conclusion are
    retained; stub prose (via `_is_stub_prose`) is dropped.
  - Every degenerate input (`None`s, strings, empty dicts) → a registry
    (possibly empty), never an exception.
- **Verify:** `python -m pytest agent/tests/test_coherence_registry.py -q`
- **Done when:** green.

### Task 1.3 — `coverage_findings` (CO1 extraction + CO2)
- **Files:** same two files.
- Tests first: replicate the shipped X2 behavior (every M3 id missing from
  `hypothesis_tests[].hypothesis`/`.id` → one soft finding with check id
  **exactly** `xtable.hypothesis_coverage` and the shipped message/location
  shape — copy the expected dict from `agent/stats_validation.py:332-338`);
  then the upgrades: `hypothesis: "H1"` covered by an entry whose only id is
  `"r-H1"` (normalized matching — the shipped exact-string version misses
  this; write the test against the NEW behavior); an orphan entry
  (`hypothesis: "H9"`, not in M3) → soft `coherence.orphan_result`; empty
  hypotheses list → `[]`; string `analysis_results` → only the M3-side
  misses (every hypothesis uncovered) — match the shipped guard's behavior
  of requiring a dict block (`agent/stats_validation.py:325`): decide and
  test explicitly — the design keeps CO1 firing only for dict blocks (a
  free-text block already gets #1's `structure.unstructured` soft finding).
- **Verify:** `python -m pytest agent/tests/test_coherence_registry.py -q`
- **Done when:** green. (Do NOT touch `agent/stats_validation.py` yet — that
  is Phase 4.)

## Phase 2 — deterministic prose extraction

### Task 2.1 — Sentence segmentation + hypothesis anchoring
- **Files:** `agent/coherence.py`, `agent/tests/test_coherence_prose.py` (new)
- Tests first (design §6.2): `"H1 was supported (β = .34, p < .001). H2 was
  not."` → two sentences, anchors H1 / H2; decimals never split
  (`"p < .05. Next"` splits, `"β = 0.34 and"` doesn't); newline always
  splits; a sentence with two anchors (`"H1 and H2 were supported"`) →
  mention evidence only (`attribution: None` for claims); Vietnamese
  sentence with "Giả thuyết H1" anchors H1.
- Implement `segment_sentences(prose)` and the anchor scan.
- **Verify:** `python -m pytest agent/tests/test_coherence_prose.py -q`
- **Done when:** green.

### Task 2.2 — Number extraction with normalization + decimals
- **Files:** same.
- Tests first (design §6.4), parameterized: `β = .34` / `beta = 0.34` /
  `hệ số hồi quy = 0,34` / `β = −0.34` (unicode minus) / `β = –0.34`
  (en-dash) → metric `beta`, values ±0.34, `decimals` 2; `p < .001` →
  threshold claim (op `<`, value 0.001, decimals 3); `p = 0.048` → exact;
  `R² = 0.56` and `R2 = 0.56` → r2; `t = 7.01`; `f² = 0.18`; a bare year
  `"(2024)"`, a percentage `"56%"`, and a citation "(Nguyen, 2020)" produce
  **no** stat claims; malformed (`β = abc`) → nothing.
- **Verify:** `python -m pytest agent/tests/test_coherence_prose.py -q`
- **Done when:** green; every emitted claim carries `metric`, `value`
  (or `threshold` + op), `decimals`, `sentence` excerpt.

### Task 2.3 — Word extraction: bilingual direction + decision lexicons
- **Files:** same.
- Tests first (design §6.3), EN + VI both: "positively affects" → positive;
  "tác động tiêu cực" → negative; "was supported" → supported; "không được
  ủng hộ" → not_supported; "not supported" never matches as "supported"
  (negated-first ordering); "significant" vs "no significant effect" vs
  "không có ý nghĩa thống kê"; a sentence containing both polarities
  ("expected a positive but found a negative effect") → no direction claim;
  NFC normalization (compose the VI test strings in decomposed form to prove
  it).
- Implement `extract_prose_claims(prose, chapter_name)` composing 2.1–2.3
  into the registry's `m5.claims` records with `attribution:
  "strong"|"weak"|None` per design §6.2 (weak = construct-label matching —
  include one weak-attribution test with a two-label sentence).
- **Verify:** `python -m pytest agent/tests/test_coherence_prose.py -q`
- **Done when:** green.

## Phase 3 — the check catalogue + entry points

### Task 3.1 — Number agreement NU1/NU2 (the hard core)
- **Files:** `agent/coherence.py`, `agent/tests/test_coherence_checks.py` (new)
- Tests first (design §5.4, §5.6): registry with stored β=0.3391 (full
  precision) + prose "β = .34" → **no** finding (half-ulp at 2 dp); prose
  "β = .31" → hard `coherence.number_mismatch` with `observed` carrying the
  sentence excerpt + parsed value, `expected` the persisted value,
  `tolerance` 0.005; sign mismatch (prose .34, stored −0.34) → hard
  regardless of ε; prose "p < .001" vs stored numeric 0.049 → hard; vs
  stored threshold `"<0.001"` → pass; vs stored 0.0004 → pass; weak
  attribution mismatch → soft `coherence.number_mismatch_weak`; R²
  attribution: unique endogenous construct → strong, two R² entries and no
  construct named → no claim; prose number with no persisted counterpart →
  no finding.
- **Verify:** `python -m pytest agent/tests/test_coherence_checks.py -q`
- **Done when:** green.

### Task 3.2 — Direction + decision + discussion checks (DI1, DI2, DE2, CO3)
- **Files:** same.
- Tests first (design §5.2, §5.3, §5.1/CO3):
  - DI1: direction positive (source `edge_effect_type`) + β=−0.30 → soft
    `coherence.direction_m3_m4`; with `decision_supported=True` the message
    contains the "cannot support" variant; direction `None` or β absent →
    skip.
  - DI2: H-anchored sentence "H1 has a significant negative effect" with
    stored β=+0.34 → soft `coherence.direction_prose`; both-polarity
    sentence → nothing.
  - DE2: "H2 was supported" with `decision_supported=False` → soft
    `coherence.decision_prose`; "H2 không được ủng hộ" with
    `decision_supported=True` → soft; hedged "partially supported" (matches
    supported only) fires against `decision_supported=False` — accept, it's
    soft; prose agrees → nothing.
  - CO3: registry entry with `m4.present=True` and no mention in results or
    discussion → soft `coherence.undiscussed_hypothesis`; fires only when
    BOTH chapters exist with non-stub prose; mention in either chapter
    suppresses it.
- **Verify:** `python -m pytest agent/tests/test_coherence_checks.py -q`
- **Done when:** green.

### Task 3.3 — Composite `check_coherence` + the two never-raising entry points
- **Files:** same.
- Tests first: `check_coherence(registry)` runs CO1–CO3, DI1–DI2, DE2,
  NU1–NU2 in that order, findings ordered by registry (M3) order then check
  order; `validate_m5_sections(final_sections, flat_context)` builds the
  registry from flat keys (`hypotheses`, `conceptual_model`,
  `analysis_results` — the flat `load()` shape, see the
  `agent/tools/state_tools.py:219-224` precedent) + incoming sections and
  returns the aggregate wrapper; `validate_coherence(nested)` reads
  `m3_design`/`m4_analysis`/`m5_writing` columns and tolerates the rubric's
  both-shape M5 (`quality/rubric.py:15-19` semantics); both entry points
  return `{"crashed": True, …}` when an internal function is monkeypatched
  to raise (never propagate); no `analysis_results` → zero findings from
  number/direction/decision/CO3 checks.
- **Verify:** `python -m pytest agent/tests/test_coherence_checks.py -q`
- **Done when:** green.

### Task 3.4 — Severity + determinism contracts
- **Files:** `agent/tests/test_coherence_checks.py`
- Tests: iterate a corpus of every mismatch type from Tasks 3.1–3.2 and
  assert `{f["check"] for f in findings if f["severity"] == "hard"} ⊆
  {"coherence.number_mismatch"}`; run `validate_m5_sections` twice on the
  same inputs → byte-identical (`json.dumps` equality) findings.
- **Verify:** `python -m pytest agent/tests/test_coherence_prose.py agent/tests/test_coherence_checks.py agent/tests/test_coherence_registry.py -q`
- **Done when:** green. Phases 1–3 complete with zero shipped-code edits.

## Phase 4 — X2 delegation in initiative #1's shipped module

### Task 4.1 — Delegate the X2 block to `coverage_findings`
- **Files:** `agent/stats_validation.py` (edit ONLY the X2 block at
  `:325-338`), `agent/tests/test_stats_validation.py` (extend)
- Tests first: add cases proving the new behavior — `hypothesis: "H1"`
  covered by a `"r-H1"`-only entry (no finding); orphan entry → soft
  `coherence.orphan_result` present in `validate_analysis_results`'s
  aggregate; the existing coverage cases in the file untouched and still
  green.
- Implement: replace the inline loop with a lazy
  `from agent.coherence import coverage_findings` +
  `findings += coverage_findings(m3_hypotheses, block)`, inside the existing
  try/except (`agent/stats_validation.py:311-342`) so a coherence-module bug
  still fails open. Signature of `validate_analysis_results` unchanged.
- **Verify:** `python -m pytest agent/tests/test_stats_validation.py agent/tests/test_state_tools.py -q`
  (both must be green — `test_state_tools.py` exercises the M4 gate's X2
  warning path end-to-end)
- **Done when:** green with no other diff in the module.

## Phase 5 — the commit gates

### Task 5.1 — M5 coherence gate in `commit_slice`
- **Files:** `agent/tools/state_tools.py` (insert the M5 block after the M4
  stats block `:104-127`, before `store.commit_slice` `:128`),
  `agent/tests/test_state_tools.py` (extend)
- Tests first (temp-dir `ProjectStateStore`, existing file pattern) — seed
  M3 (`hypotheses` + `conceptual_model`) and M4 (`analysis_results` with the
  skill's sample block) via direct store commits, then:
  1. M5 commit whose results-chapter prose quotes "β = .34, p < .001" for H1
     (matching state) → succeeds, no `coherence_warnings` key... unless CO3
     fires for other hypotheses — use a single-hypothesis seed so the clean
     case is truly clean.
  2. Prose quoting "β = .55" for H1 → returns
     `{"error": "coherence_failed…", "findings": [...]}` and `store.load()`
     shows `final_sections` unchanged.
  3. Prose saying "H1 was not supported" against `decision: "supported"` →
     commit **succeeds**, result carries `coherence_warnings` with
     `coherence.decision_prose`.
  4. No `analysis_results` in the store → M5 commit passes with no
     coherence keys.
  5. Monkeypatch `agent.coherence.validate_m5_sections` to raise → commit
     succeeds, result carries `coherence: "unavailable"`.
  6. M1–M4 commits and M5 commits without `final_sections` in `writes` →
     byte-identical behavior to before (no coherence import triggered —
     assert via monkeypatched import hook or simply absence of the keys).
- Implement per the design §7.2 code sketch: lazy import, `_agg` contract,
  error JSON with the `hint` text, `coherence_warnings` /
  `coherence: "unavailable"` keys attached the same way `_stats_warnings`
  is (`state_tools.py:140-142`).
- **Verify:** `python -m pytest agent/tests/test_state_tools.py -q`
- **Done when:** all scenarios green; then `python -m pytest agent/tests -q`
  fully green.

### Task 5.2 — Advisory DI1 at the M4 gate
- **Files:** `agent/tools/state_tools.py` (extend the M4 block),
  `agent/tests/test_state_tools.py` (extend)
- Tests first: M4 commit with `conceptual_model` seeded (H1 edge
  `effect_type: "positive"`) and `hypothesis_tests` β=−0.30,
  decision "supported" → commit **succeeds** (stats validation passes — the
  numbers are possible) and the result carries `coherence_warnings`
  containing `coherence.direction_m3_m4`; a crash in the coherence call →
  commit unaffected, no warnings key; hard coherence never fires at M4 (by
  construction — assert no `coherence_failed` error possible from an M4
  commit in these tests).
- Implement `m4_commit_findings(analysis_results, flat_context)` in
  `agent/coherence.py` (soft-only: DI1 over the registry built without M5)
  plus the gate merge under `coherence_warnings`, wrapped in try/except.
- **Verify:** `python -m pytest agent/tests/test_state_tools.py agent/tests/test_coherence_checks.py -q`
- **Done when:** green.

## Phase 6 — the rubric dimension

### Task 6.1 — `coherence_dimension` + blocking wiring
- **Files:** `quality/rubric.py` (new dimension function + one `dims.append`
  in `score_thesis` after `:457`), `tests/test_coherence_dimension.py` (new)
- Tests first (pattern: `tests/test_stats_validity_dimension.py`):
  - A synthetic nested store (reuse that file's `GOOD` M4 block, add
    `m3_design.{hypotheses, conceptual_model}` and an `m5_writing.chapters`
    results+discussion with matching quotes) → `score == 1.0`, no findings,
    `weight == 0.10`, name `"coherence"`.
  - Corrupt the prose β → one hard finding, score 0.5, and — via
    `score_thesis` with judge dimensions monkeypatched (see how
    `tests/test_quality_gate.py` stubs `judge_dimension`/LLM) — the message
    appears in `blocking`.
  - Prose-decision mismatch → soft finding, score 0.9, NOT in `blocking`.
  - `m5_writing` missing / `analysis_results` a string / hypotheses strings →
    no crash, sensible scores.
  - `tests/good_pls_thesis.json` through `coherence_dimension` → **zero
    hard** findings (soft permitted; if any hard fires, the extraction is
    over-eager — fix the extractor, do not touch the fixture).
- Implement per design §7.4: lazy `from agent.coherence import
  validate_coherence`, finding mapping with per-check `fix` templates,
  0.5/0.1 scoring floored at 0, never-crash try/except with
  `logger.exception`.
- **Verify:** `python -m pytest tests/test_coherence_dimension.py tests/test_stats_validity_dimension.py tests/test_quality_gate.py -q`
- **Done when:** green, including the two pre-existing rubric suites.

## Phase 7 — skill + docs surface

### Task 7.1 — M5 skill, M4 skill, AGENTS.md
- **Files:** `skills/dothesis-m5-writing/SKILL.md`,
  `skills/dothesis-m4-analysis/SKILL.md`, `AGENTS.md`
- Content per design §7.6:
  - M5 skill: the "Numbers come from state" section (read M4 slice → quote
    verbatim at displayed precision; `coherence_failed` recovery — re-read
    and correct, or recommit M4; never split the difference; acknowledge
    `coherence_warnings` before `confirm_done`). Place it adjacent to the
    existing "Saving final_sections — the hard rule" section (`:154`) so the
    two commit-contract rules read together.
  - M4 skill: extend the soft-finding bullet (`:190-192`) with the
    orphan-result direction of coverage.
  - AGENTS.md invariants row (design §7.6 wording).
- **Verify:** `grep -n "coherence" skills/dothesis-m5-writing/SKILL.md skills/dothesis-m4-analysis/SKILL.md AGENTS.md` shows the three additions; no test suite involvement.
- **Done when:** prose reviewed against the design's contracts (severities,
  key names) — a skill that promises a behavior the gate doesn't have is a
  bug.

## Phase 8 — full verification

### Task 8.1 — Whole-suite regression + determinism smoke
- **Verify (all must pass, run in order):**
  1. `python -m pytest agent/tests -q`
  2. `python -m pytest tests/test_coherence_dimension.py tests/test_stats_validity_dimension.py tests/test_quality_gate.py -q`
  3. `python -m pytest libs/thesis-stats/tests -q` (must be untouched-green —
     this plan never edits the submodule; a failure here means scope creep)
  4. Determinism smoke: `python - <<'EOF'` … build the Task 6.1 synthetic
     store, run `validate_coherence` twice, assert `json.dumps` equality …
     `EOF`
- **Done when:** all green. Deliverable checklist against the design:
  registry (§4) ✓, catalogue with NU1-only-hard (§5) ✓, M5 gate blocks /
  M4 advisory / rubric blocking (§7) ✓, X2 delegated not duplicated (§7.3) ✓,
  bilingual extraction (§6.3) ✓, fail-open everywhere (§8) ✓, offline tests
  only (§9) ✓.
