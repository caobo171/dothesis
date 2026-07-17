# Rubric-Grounded Viva Simulation — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-viva-simulation-design.md` (read it first — the targeting model §4, difficulty table §5, defensibility §6, template table §7, envelope §8, and LLM-boundary decision §9 are normative there; this plan only sequences them).
**Executor notes:** All paths relative to the dothesis repo root; run commands from there unless a `cd api` is written. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–2 are a pure module with zero wiring; Phase 3 is the only task that edits the shipped tool — its existing suite must go green (updated) in the same task. Offline only: no network, no LLM calls, no `integration` marker; the one test that exercises the real `score_thesis` stubs the judge LLM exactly as `api/tests/test_defense.py:47-53` already does.

**Hard constraints (from the design):**
- `agent/viva.py` is pure: stdlib at module scope plus (lazily, inside functions, if needed at all) `agent.coherence.normalize_hypothesis_id`. No LangChain, no `quality.*` import, no I/O, no clock, no LLM. `generate_viva` never raises.
- Zero LLM calls anywhere in the generator (design §9). The only LLM touchpoints remain `score_thesis`'s judge dims (called best-effort by the tool, unchanged) and the skill's drill voice.
- Never fabricate: every non-staple question carries `grounding` whose `issue` is verbatim from the input rubric finding or whose `values` are read from state — enforced by the Task 2.2 property test.
- Judge-failure placeholders (`issue` starting `"Could not evaluate"`, `quality/rubric.py:211-213`) never become questions.
- Caps: ≤ 3 questions per rubric dimension (hard first), ≤ 30 total; dedup on `(category, issue)`.
- Output ordering deterministic (design §8); two calls on equal input are byte-identical after `json.dumps(..., sort_keys=True)`.
- Advisory only: no `commit_slice`, no status/focus writes, tool stays read-only.

---

## Phase 1 — pure viva core (`agent/viva.py`)

### Task 1.1 — Rubric-finding → question mapping
- **Files:** `agent/viva.py` (new), `agent/tests/test_viva.py` (new)
- Tests first (hand-built `rubric_result` fixtures, shape per `quality/rubric.py:510-514`):
  - `rubric_questions(rubric_result) -> list[dict]`: one finding per dimension for `coherence` (hard), `stats_validity` (hard), `citations` (hard), `advisor` (hard), `similarity` (soft), `source_verification` (soft), `preflight` (soft), `instrument_quality` (soft), `results_validity` (soft) → each yields exactly one question with the design-§7 template's category, `difficulty` (`hard`→`hard`, `soft`→`medium` per §5), `defensibility` (`hard`→`must_fix`, `soft`→`disclosable` per §6), a `model_answer_hint` that **contains the finding's `fix` string verbatim**, non-empty `answer_criteria` (2–4 strings), and `grounding == {"source": f"rubric:{dim}", "severity": …, "issue": <verbatim>, "chapter": …, "values": None}`.
  - Unknown dimension name (`"future_dim"`) → the generic fallback phrasing (parity with today's `agent/tools/defense.py:80-83`), not a drop.
  - Judge placeholder skipped: a `writing` dim finding `{"issue": "Could not evaluate writing automatically.", …}` yields zero questions.
  - Caps + dedup: 30 identical-`issue` citation findings → 1 question; 5 distinct-`issue` citation findings → 3 questions, hard ones first.
  - Findings missing `fix`/`chapter` keys → question still emitted (safe defaults; today's `.get` posture, `agent/tools/defense.py:79-83`).
- **Verify:** `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** green; `python -c "import agent.viva"` succeeds in a subprocess with `langchain` and `quality` absent from `sys.modules` (assert in a test — precedent: the import-purity tests noted in `docs/superpowers/specs/2026-07-17-similarity-plan.md` Task 1.1).

### Task 1.2 — State-direct signals
- **Files:** `agent/viva.py`, `agent/tests/test_viva.py`
- Tests first (nested store shape per `api/app/agent_state.py:157-171`):
  - `state_signal_questions(cs) -> list[dict]`, power shortfall: `m3_design.sample_plan = {"target_n": 160, "power_analysis": {"required_n": 160, "justification": "Using the inverse square root method (Kock & Hadaya, 2018)…"}}` + `m4_analysis.analysis_results.descriptives.n = 95` → one `methodology` question, `difficulty: "hard"` (shortfall ≥ 20%), `defensibility: "disclosable"`, hint containing both `95` and `160` and the justification's citation text, `grounding.values == {"n_achieved": 95, "required_n": 160}`. Shortfall < 20% (n=150 vs 160) → `medium`. `recommended_n` present → used over `required_n` (design §4.B; `libs/thesis-stats/src/thesis_stats/power.py:202-207`). Achieved n fallback to `len(field_it_responses)` when `descriptives.n` absent.
  - No `power_analysis`, `target_n=90` → exactly the legacy small-n question (one, not two — mutual exclusion; parity with `agent/tools/defense.py:33-39`).
  - Structured hypothesis decisions: `hypothesis_tests` with H1 supported, H2 `"not supported"`, H3 `"Rejected"` → two `results` questions (H2, H3), each `hard`/`disclosable`, question text carrying the id, `path`, and `numbers.beta`/`p` when present (`skills/dothesis-m4-analysis/SKILL.md:165-172` shape); decision normalization mirrors `agent/coherence.py:241` (`startswith("support")`). Cap 3 with 5 not-supported hypotheses.
  - Legacy string `analysis_results = "H1 not supported (p=0.21)"` → the old substring question survives (parity with `agent/tools/defense.py:42-49`).
  - `field_it_quality = [{"x": 1}, {"y": 2}]` → one `data_quality` question, `medium`/`disclosable`, hint carrying the count `2`; entries are never dereferenced (a list of junk types must not crash — `agent/state.py:439-450` gives no entry schema).
  - Staples: always exactly 4 (contribution, method justification, limitations, generalizability), `defensibility: "standard"`, `grounding.source == "staple"`; generalizability interpolates `m1_topic.target_population`/`scope` when present, generic otherwise.
- **Verify:** `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** green.

### Task 1.3 — Envelope assembly: `generate_viva`
- **Files:** `agent/viva.py`, `agent/tests/test_viva.py`
- Tests first:
  - `generate_viva(cs, rubric_result=None) -> dict` returns the §8 envelope: `questions` ordered must_fix → disclosable → standard, stable within groups (input dimension order, then finding index); sequential unique `id`s; `meta.rubric_available` true/false tracking whether a usable `rubric_result` was passed; `meta.method` copied from `rubric_result["method"]` when present else `None`; `meta.generator == "viva-v2-deterministic"`.
  - `readiness(questions)`: mixed fixture (2 hard rubric findings, 3 soft, 1 power shortfall) → `{"verdict": "not_ready", "must_fix": 2, "disclosable": 4, …}`; zero must_fix + ≥1 disclosable → `"ready_with_disclosures"`; staples only → `"ready"`. `by_dimension` counts **all** input findings, including those beyond the per-dimension question cap (30 citation findings → `by_dimension["citations"] == 30` while only ≤ 3 questions exist). `summary` is a deterministic sentence containing both counts.
  - Determinism: two calls on `copy.deepcopy`-equal inputs → `json.dumps(..., sort_keys=True)` byte-equal.
- **Verify:** `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** green.

## Phase 2 — robustness + the never-fabricate property

### Task 2.1 — Never-crash on partial/junk state
- **Files:** `agent/tests/test_viva.py`
- Tests first: `generate_viva({})`, `generate_viva(None)`, and a store of junk-typed slices (`m3_design: "oops"`, `m4_analysis: {"analysis_results": 42, "field_it_quality": "nope"}`, `sample_plan: {"power_analysis": {"required_n": "many"}}`) each return a valid envelope: 4 staples, `verdict: "ready"`, no exception. A malformed `rubric_result` (`{"dimensions": "x"}`, findings as strings) degrades to state-only questions. Posture parity: `agent/coherence.py:478+` / `quality/rubric.py` fail-open.
- **Verify:** `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** green.

### Task 2.2 — Never-fabricate property test
- **Files:** `agent/tests/test_viva.py`
- Test first: a seeded generator builds ~50 randomized (rubric_result, cs) pairs (random subsets of dimensions/findings/signals, seeded `random.Random(0)`); for every emitted question with `grounding.source != "staple"`: `rubric:*` → `grounding.issue` appears verbatim among the input findings' `issue` strings; `state:*` → every value in `grounding.values` is reachable in the input store (assert directly against the fixture values). No question ever references a dimension/signal absent from the input.
- **Verify:** `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** green; this test would fail if anyone later adds an LLM/template path that invents weaknesses.

## Phase 3 — wire the tool (`agent/tools/defense.py`)

### Task 3.1 — Caller audit, then delegate
- **Files:** `agent/tools/defense.py`, `api/tests/test_defense.py`
- First: `grep -rn "committee_questions\|make_defense_tools\|generate_committee_questions" --include="*.py" --include="*.md" .` — expected hits only in `agent/tools/defense.py`, `agent/runtime.py:162,540`, `api/tests/test_defense.py`, `skills/dothesis-defense/SKILL.md`, and specs. Any new hit → decide compat there before proceeding.
- Tests first (rewrite `api/tests/test_defense.py` to the new contract; keep its judge-stub monkeypatch pattern `:47-53`):
  - `committee_questions(cs, rubric_result=None)` still returns a **list** (back-compat pure API, now `generate_viva(...)["questions"]`); existing assertions (small-n + not-supported targeting `:15-23`, empty-state ≥ 3 → now ≥ 4 staples `:26-28`, rubric-finding targeting `:31-39`) updated to the new phrasing/fields, same spirit.
  - The **tool** `generate_committee_questions` now returns the full envelope JSON: `json.loads(...)` has `questions`, `readiness`, `meta`; store-bound wiring test extended — the `_Store` fixture (`:55-66`) with a hard-finding-producing state yields `readiness.verdict == "not_ready"` … actually with judge stubbed and that minimal store, assert the envelope shape + that `questions` is non-empty and `meta.rubric_available is True`.
  - Rubric-failure fallback: monkeypatch `quality.rubric.score_thesis` to raise → tool still returns an envelope, `meta.rubric_available is False`, staples + state questions present (parity with `agent/tools/defense.py:105-113` best-effort contract).
- Then: `_state_weakpoints` and the old inline rubric-folding in `committee_questions` (`:66-84`) are replaced by delegation to `agent.viva`; `make_defense_tools` keeps the factory shape (`:87-116`), keeps the try/except around `score_thesis`, and dumps the envelope. Update the tool docstring (it is the model-facing contract) to mention readiness + defensibility.
- **Verify:** `cd api && python -m pytest tests/test_defense.py -q` and `python -m pytest agent/tests/test_viva.py -q`
- **Done when:** both green; grep from step 1 shows no un-updated consumer.

### Task 3.2 — Tool-adjacent regression sweep
- **Files:** none (verification task)
- **Verify:** `python -m pytest agent/tests -q` and `cd api && python -m pytest tests -q` and `python -m pytest -q` (root `tests/`, `pytest.ini` testpaths)
- **Done when:** all green — proves the delegation changed no unrelated behavior (roadmap defense-prep card `agent/roadmap.py:138-143` and `tests/test_quality_gate.py` untouched).

## Phase 4 — the drill surface (`skills/dothesis-defense/SKILL.md`)

### Task 4.1 — Readiness-first flow + criteria grading
- **Files:** `skills/dothesis-defense/SKILL.md`
- No pytest here (prompt copy); review against the design §9.3 checklist:
  - Step 1 now: call the tool, then **lead with `readiness`** — if `verdict == "not_ready"`, present the must_fix questions as "the committee will find these; fix them first" and route each to its owning module (coherence/stats → M4/M5, citations → M2/M5, advisor → its chapter) before drilling; never drill a must_fix as if it were defensible.
  - Step 2 (drill): grade each answer **against the question's `answer_criteria`, criterion by criterion** (met / missed), then coach — replaces free-form grading vs `model_answer_hint`; hint stays the coaching target text. Keep: one question at a time, `[OPTIONS]` marker, student's language, encouraging tone.
  - Step 3 (cheat-sheet): unchanged export path (`export_docx`), but the sheet opens with the readiness line (X must-fix, Y disclosable) and groups by defensibility.
  - Boundaries section: unchanged (read-only, best-effort, encouraging) — re-assert the tool may now return `must_fix` items and the skill still never blocks or writes state.
- **Verify:** manual read-through + `cd api && python -m pytest tests/test_defense.py -q` still green (skill edits touch no code).
- **Done when:** SKILL.md references `readiness`, `defensibility`, and `answer_criteria` by name and contains no stale claim that the tool returns a bare question list.

## Phase 5 — end-to-end fixtures

### Task 5.1 — Dirty-thesis integration test (real `score_thesis`, stubbed judge)
- **Files:** `api/tests/test_defense.py` (or `api/tests/test_viva_integration.py`, new)
- Test first: build one synthetic **nested** store engineered to trigger findings across ≥ 4 deterministic dimensions — e.g. a `final_sections` chapter quoting β=.45 for H2 where `analysis_results.hypothesis_tests` records .34 (coherence hard, `quality/rubric.py:430-452`), an `analysis_results.measurement_model` entry with AVE inconsistent with its own loadings (stats_validity hard, `:257-288`), prose citing `(Ghost, 2099)` absent from `literature_sources` (citations hard, `:43-63`), `sample_plan.power_analysis.required_n=160` with `descriptives.n=95` (state signal), one open `advisor_feedback` directive passed through the store's `get_advisor_feedback` (advisor hard, `:233-247`). Monkeypatch the judge (`orchestrator.tools.m5_writing._get_llm`, pattern `api/tests/test_defense.py:47-53`). Call the tool; assert: every rubric `blocking` entry has a matching `must_fix` question (match on `grounding.issue`), the power question carries 95/160 in its hint, `readiness.verdict == "not_ready"`, and counts are consistent (`must_fix == len(<hard-grounded questions>)`).
- **Verify:** `cd api && python -m pytest tests/test_defense.py tests/test_viva_integration.py -q`
- **Done when:** green offline (no network; DOI layer stays off by default — `quality/rubric.py:294-296, :358-361`).

### Task 5.2 — Clean-thesis test + determinism at the tool boundary
- **Files:** same test file
- Tests first: a healthy store (all chapters present, coherent numbers, cited sources, `n ≥ recommended_n`, no advisor items, judge stubbed to `{"score": 0.9, "findings": []}`) → questions are exactly the 4 staples (+ any soft findings the fixture legitimately triggers — engineer it so there are none), `readiness.verdict == "ready"`, `must_fix == 0`. Two tool invocations on the same store return byte-identical JSON.
- **Verify:** `cd api && python -m pytest tests/ -q` and `python -m pytest agent/tests -q` and `python -m pytest -q`
- **Done when:** all suites green. Initiative complete: deterministic core + envelope + readiness shipped, skill drills against criteria, zero new LLM calls, nothing blocks.

---

## Explicitly not in this plan (design §12)
Grading tool / iterate-until-pass automation; M5 limitations preemption feed; degree-level difficulty; any rubric→viva reverse dependency or report UI work.
