# M1 Topic Feasibility — Implementation Plan (TDD)

**Date:** 2026-07-18
**Design:** `2026-07-18-m1-feasibility-design.md` (normative — read it first; D-numbers below refer to its decisions)
**Executor:** Opus agent. Strict TDD: in every phase, write the failing tests first, run them to see them fail, then implement to green. Never modify `libs/thesis-stats` (pure reuse).

Conventions used below:
- Repo root: `/Users/caonguyenvan/project/dothesis`. All paths relative to it.
- Test runner: `pytest <path> -q` (repo `pytest.ini` scopes `testpaths=tests`, so agent tests are always run by explicit path — see existing `agent/tests/`).
- Guard engine-dependent tests with `pytest.importorskip("thesis_stats")` (pattern: `agent/tests/test_sampling_plan_power.py:7`).
- Fake-store pattern for tool tests: `ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")` + `make_*_tool(store).func()` (pattern: `agent/tests/test_sampling_plan_power.py:13-19,35-36`).

---

## Phase 0 — Capture goldens (no production code)

**Task 0.1 — Verify the shipped power engine's outputs for the M1 defaults.**
- Files: none (throwaway script OK, do not commit it).
- Do: with the project's Python environment, run
  `python -c "import thesis_stats as ts; print(ts.run_power('pls_sem','apriori',effect_size='medium',predictors=2)); print(ts.run_power('regression','apriori',effect_size='medium',predictors=3)); print(ts.run_power('regression','apriori',effect_size='medium',predictors=4))"`
  (add `libs/thesis-stats/src` to `sys.path` if the submodule isn't installed).
- Record: PLS medium → `required_n` (expected **155** per
  `power.py:197-204`), regression medium k=3 → **77** (shipped golden,
  `libs/thesis-stats/tests/test_power.py:12-18`), regression medium k=4 →
  the exact N (expected ≈85; use whatever the lib prints).
- Done when: the three numbers are captured for use as test goldens in
  Phase 1. If any differ from the expectations above, STOP and reconcile with
  the design doc before proceeding.

---

## Phase 1 — Pure sample-size core (tests first)

**Task 1.1 — Failing tests for `estimate_sample_size`.**
- Files: create `agent/tests/test_feasibility.py`.
- Write tests (design §8, items 1-3, 7-10 for the sample-size half):
  - `test_pls_hint_three_constructs`: `estimate_sample_size({"research_type":
    "quantitative"}, expected_constructs=3, method_hint="PLS-SEM")` →
    `status=="estimate"`, `basis=="power"`, one estimate with
    `analysis=="pls_sem"`, `required_n==155`, `"Kock & Hadaya" in
    justification`, `assumed["predictors"]==2`,
    `assumed["predictors_source"]=="student_stated"`.
  - `test_regression_hint_k3`: `method_hint="SPSS regression"`,
    `expected_constructs=4` → `required_n==77`, justification mentions
    `f²`-flavored citation ("Cohen"), `analysis=="regression"`.
  - `test_no_hints_range`: m1 with 3 relationship RQs (e.g. "To what extent
    does price affect loyalty?" ×3 variants) → `status=="range"`,
    `assumed["predictors"]==3`,
    `assumed["predictors_source"]=="inferred_from_rqs"`, `len(estimates)==2`
    (both families), `range==[min,max]` of the two Ns,
    `headline_n==max(range)`.
  - `test_default_k_when_empty`: `estimate_sample_size({})` →
    `status=="range"`, `assumed["predictors"]==4`,
    `predictors_source=="default"`, message contains
    `"your intended population"`, no exception.
  - `test_population_interpolated`: m1 with
    `target_population="Gen Z bank customers in Hanoi"` → that exact string in
    `message`.
  - `test_qualitative_skipped`: `research_type="qualitative"` →
    `status=="skipped"`, `skipped_reason` non-empty, no `estimates`.
  - `test_cbsem_hint_heuristic`: `method_hint="CB-SEM (AMOS)"` →
    `basis=="heuristic"`, `headline_n>=200` (Kline floor,
    `agent/sampling.py:22`), no crash despite the power engine lacking cb_sem.
  - `test_deterministic`: two identical calls → equal dicts.
  - `test_fail_open_power_raises`: monkeypatch `thesis_stats.run_power` to
    raise → `basis=="heuristic"`, well-formed payload, no exception.
  - Assert everywhere: return is a plain dict, `"advisory"` semantics
    preserved (no key named `blocked`/`ready`), and the justification string —
    when `basis=="power"` — is byte-identical to
    `thesis_stats.run_power(...)["justification"]` for the same params (D5).
- Verify: `pytest agent/tests/test_feasibility.py -q` → all FAIL
  (module doesn't exist yet).
- Done when: tests exist, fail for the right reason (ImportError/AttributeError
  on `agent.feasibility`).

**Task 1.2 — Implement `agent/feasibility.py::estimate_sample_size`.**
- Files: create `agent/feasibility.py`.
- Implement per design §3 (D2, D3, D4, D6) and §4.1:
  - Module docstring: pure/deterministic/advisory/never-raises, in the voice
    of `agent/preflight.py:1-14` and `agent/coherence.py:1-12`.
  - k ladder (D2): explicit `expected_constructs-1` → relationship-marker RQ
    count clamp(2,8) → default 4; clamp k to [1,12].
  - Method resolution via `agent.method_advisor.normalize_method`
    (`agent/method_advisor.py:29-41`). Import at module top (pure, no cycle:
    method_advisor imports nothing from tools).
  - Power calls: `import thesis_stats as ts` **inside** the function
    (lazy, so the module imports even without the submodule — mirrors
    `agent/tools/instrument.py:225`), `ts.run_power(analysis, "apriori",
    effect_size="medium", predictors=k)`. Use `recommended_n or required_n`
    when picking each family's N (mirrors `instrument.py:228`).
  - Degradation ladder (D6): try power → except: `from agent.sampling import
    target_sample_n` heuristic (`agent/sampling.py:12-26`; map family →
    method string, pass `n_paths=k`, `n_indicators=0`) → except: canned
    `[100, 200]`. Outermost `try/except Exception` returns the canned shape —
    the function literally cannot raise.
  - Message template per §4.1: interpolate `target_population` or
    "your intended population"; always end with the M3 hand-off sentence
    ("M3 will compute the exact figure from your actual model.") (D10).
- Verify: `pytest agent/tests/test_feasibility.py -q` → sample-size tests
  PASS. Then `pytest agent/tests/test_sampling_plan_power.py -q` still green
  (nothing touched, but prove it).
- Done when: all Phase-1 tests green; `estimate_sample_size` has no LLM /
  network / file I/O imports (grep the module for `httpx|requests|langchain|
  llm|open(` → only the lazy `thesis_stats`/`agent.sampling` imports).

---

## Phase 2 — Operationalizability core (tests first)

**Task 2.1 — Failing tests for `check_operationalizability`.**
- Files: extend `agent/tests/test_feasibility.py`.
- Tests (design §8 items 4-6 + D7):
  - `"What is the meaning of leadership?"` → exactly one finding,
    `kind=="definitional"`, `severity=="advisory"`, `reframe_hint` non-empty.
  - Mixed list: the definitional RQ + `"To what extent does transformational
    leadership affect employee engagement?"` → only the first flagged;
    `testable_count==1`, `total==2`.
  - `"Should companies ban remote work?"` → `kind=="normative"`.
  - All-descriptive set (2 definitional RQs) + `research_type="quantitative"`
    → includes a `topic_not_testable` finding; same set with
    `research_type="qualitative"` → no `topic_not_testable`.
  - Vietnamese: `"Chuyển đổi số ảnh hưởng như thế nào đến hiệu quả làm việc?"`
    → not flagged (relationship marker `ảnh hưởng`);
    `"Lãnh đạo là gì?"` → `definitional`.
  - `"How does X change Y?"`-style with no lexicon hit but also no
    descriptive trigger → `kind=="no_measurable_relationship"` (soft).
  - Defensive: `check_operationalizability(None)`,
    `check_operationalizability([None, 42, ""])` → no exception, well-formed
    payload.
  - Determinism: repeated call equality.
- Verify: `pytest agent/tests/test_feasibility.py -q` → new tests FAIL.
- Done when: failing for the right reason.

**Task 2.2 — Implement `check_operationalizability` in `agent/feasibility.py`.**
- Implement per D7/§4.2: NFC-normalize + casefold; three finding kinds with
  the precedence definitional > normative > relationship-present(ok) >
  no_measurable_relationship; EN+VI lexicons as module-level compiled regex
  tuples; topic-level `topic_not_testable` when zero relationship markers and
  research_type not qualitative. Expose the relationship-marker predicate as a
  private helper `_has_relationship_marker(text) -> bool` and REUSE it from
  `estimate_sample_size`'s k-ladder step 2 (single lexicon, D2/D7 shared).
- stdlib only (`re`, `unicodedata`). Never raises.
- Verify: `pytest agent/tests/test_feasibility.py -q` → all green.
- Done when: green + the k-inference test from Phase 1
  (`test_no_hints_range`) still passes using the shared predicate.

---

## Phase 3 — Store-bound tool + state ownership + runtime wiring (tests first)

**Task 3.1 — Failing tool tests.**
- Files: extend `agent/tests/test_feasibility.py`.
- Tests (design §8 item 11; fake-store pattern
  `agent/tests/test_sampling_plan_power.py:13-19`):
  - Seed a `ProjectStateStore(tmp_path/…)` with an M1 commit
    (`research_title`, `research_questions` incl. one definitional RQ,
    `target_population`, `research_type="quantitative"`); call
    `make_feasibility_tool(store).func(expected_constructs=3,
    method_hint="PLS")`; parse the JSON: `sample_size.headline_n==155`,
    `operationalizability.findings` non-empty, `advisory is True`.
  - Persistence: after the call,
    `store.load()["contextStore"]["feasibility"]` exists and carries
    `inputs.predictors_source=="student_stated"`.
  - Fail-open persistence: a stub store whose `commit_slice` raises but whose
    `load` works → tool still returns valid JSON (mirrors
    `agent/tools/instrument.py:252-256`).
  - No-args call on an empty store → valid JSON, `status=="range"`, no
    exception.
- Also add an ownership unit test: `"feasibility" in
  SLICE_OWNERSHIP["M1"]` (`agent/state.py`).
- Verify: `pytest agent/tests/test_feasibility.py -q` → new tests FAIL
  (no factory, no ownership).
- Done when: failing for the right reason.

**Task 3.2 — Implement `make_feasibility_tool` + ownership + registration.**
- Files: `agent/feasibility.py` (factory), `agent/state.py`,
  `agent/runtime.py`.
- `agent/state.py:35-37`: append `"feasibility"` to `SLICE_OWNERSHIP["M1"]`
  with a one-line comment (advisory early sample-size estimate; advertised in
  the skill slice map, unlike `decisions` — see the existing comments in that
  block for the distinction).
- Factory per §4.3: `@tool def topic_feasibility(expected_constructs: int = 0,
  method_hint: str = "") -> str`; reads
  `(store.load() or {}).get("contextStore") or {}` (flat-store read,
  `agent/preflight.py:88-89`); builds the m1 view from top-level keys; calls
  the two pure functions; persists via
  `store.commit_slice("M1", {"feasibility": …}, reason="topic_feasibility:
  early sample-size reality check")` inside try/except with
  `logger.exception` (pattern `agent/tools/instrument.py:249-256`); returns
  `json.dumps(payload, ensure_ascii=False)`. Docstring: advisory, run ONCE
  before locking the topic; pass hints only if the student stated them.
- `agent/runtime.py`: import `make_feasibility_tool` and register
  `make_feasibility_tool(store)` in the tools list adjacent to
  `make_preflight_tool(store)` (`agent/runtime.py:516-518`) with a short
  comment (vision §3.1: M1 feasibility — early n reality check +
  operationalizability, advisory).
- Verify: `pytest agent/tests/test_feasibility.py agent/tests/test_state_store.py agent/tests/test_state_tools.py -q`
  → green (state tests prove ownership change broke nothing). Then a smoke
  import: `python -c "import agent.runtime"` (or the repo-equivalent) exits 0.
- Done when: all green; `git diff agent/runtime.py` shows only the import +
  one registration block.

---

## Phase 4 — Skill copy (skills-first surface)

**Task 4.1 — M1 skill: present once, early, actionable.**
- Files: `skills/dothesis-m1-topic/SKILL.md`.
- Edit per design D9:
  - In **Phase 4 — Confirm and commit** (`SKILL.md:84-88`): before asking
    "Lock this in?", add the one-time `topic_feasibility` call instruction:
    pass `expected_constructs`/`method_hint` only if the student volunteered
    them; present the reality-check question with the population interpolated
    and the verbatim justification sentence offered as "the sentence you'll
    later paste into Chapter 3"; present at most the top 2
    operationalizability findings with reframe hints; if the student proceeds
    anyway, commit without further comment. Explicitly: run it once per
    topic — never re-run on later passes unless a substantial pivot
    (`SKILL.md:30-33` trigger).
  - Add one row to the **Quality bars** table (`SKILL.md:98-106`):
    "Feasibility is advice, not a gate | Never refuse to commit a topic over
    sample size or operationalizability — flag warmly, once."
  - Add one ❌ line to **What you do NOT do** (`SKILL.md:117-123`): "Do not
    nag about feasibility — one check, at topic-lock, then respect the
    student's call."
  - Mirror the language rule: deliver the advice in the student's language;
    keep the justification sentence's English form available (design D5).
- Files: `skills/dothesis/SKILL.md` — add `feasibility` to the M1 row of the
  slice map (`:178`), keeping the `agent/state.py:22-23` sync contract.
- Verify: no automated gate for skill copy; re-read both diffs against design
  D9 and confirm the slice map now matches `SLICE_OWNERSHIP["M1"]` minus the
  deliberately-hidden keys (`decisions`, `user_context` — see
  `agent/state.py:25-34` comments; do NOT add those).
- Done when: both SKILL.md diffs match D9; no other skill files touched.

---

## Phase 5 — M3 reconciliation (tests first)

**Task 5.1 — Failing test: sampling_plan references the M1 estimate.**
- Files: extend `agent/tests/test_sampling_plan_power.py` (it already owns
  sampling_plan behavior).
- Test: seed a store with an M1 `feasibility` commit (headline_n, assumed k)
  AND the existing `_MODEL` M3 seed (`:22-27`); run
  `make_sampling_plan_tool(store).func()`; assert the returned plan's
  `rationale` contains the early-estimate sentence (e.g. `"Early M1 estimate"`)
  and the M1 headline number. Also assert a store with NO `feasibility` key
  produces a rationale WITHOUT that sentence (no regression for existing
  users).
- Verify: `pytest agent/tests/test_sampling_plan_power.py -q` → new tests
  FAIL, old ones green.

**Task 5.2 — Implement the one-sentence reconciliation.**
- Files: `agent/tools/instrument.py` (inside `sampling_plan`, after the
  rationale is composed, `:235-238`).
- Read `feas = cs.get("feasibility") or {}`; if it carries a usable
  `sample_size.headline_n`, append: `"Early M1 estimate was n ≈ {X} (assumed
  {k} predictors); this plan supersedes it."` Wrap in try/except — malformed
  feasibility state must never break sampling_plan (design D10.3, D6).
- Verify: `pytest agent/tests/test_sampling_plan_power.py agent/tests/test_feasibility.py -q` → all green.
- Done when: green; `agent/preflight.py` untouched (design D10.4).

---

## Phase 6 — Full verification + hygiene

**Task 6.1 — Whole-surface regression run.**
- Verify:
  `pytest agent/tests -q` → green (or identical pre-existing failures only —
  record any that predate the branch);
  `pytest libs/thesis-stats/tests/test_power.py -q` → green and UNTOUCHED
  (`git diff libs/` must be empty).
- Determinism spot-check: run `pytest agent/tests/test_feasibility.py -q`
  twice; identical results.
- Done when: green; `git status` shows changes ONLY in: `agent/feasibility.py`
  (new), `agent/tests/test_feasibility.py` (new), `agent/state.py`,
  `agent/runtime.py`, `agent/tools/instrument.py`,
  `agent/tests/test_sampling_plan_power.py`, `skills/dothesis-m1-topic/SKILL.md`,
  `skills/dothesis/SKILL.md`, plus these two spec docs.

**Task 6.2 — Self-review against the design's invariants.**
- Checklist (all must hold; cite the design section if any fails and STOP):
  - [ ] No code path can block the M1 commit (D6; grep `agent/feasibility.py`
        for `raise` — allowed only inside caught scopes).
  - [ ] Justification sentence surfaces verbatim from `run_power` (D5).
  - [ ] Effect-size convention is `"medium"` everywhere, matching
        `agent/tools/instrument.py:226` (D4).
  - [ ] No edits to `libs/thesis-stats`, `agent/preflight.py` logic, or the
        `OPS` whitelist in `agent/tools/stats.py` (D1, D10.4, §7).
  - [ ] `feasibility` ownership + skill slice map in sync (D8).
- Done when: checklist clean. Then follow the repo's normal finishing flow
  (branch/commit/PR per `CONTRIBUTING.md`); do not merge without the user.

---

## Phase order rationale

Pure core first (Phases 1-2) so every decision in the design is pinned by
offline tests before any store/agent surface exists; tool + state wiring
(Phase 3) only consumes an already-green core; skill copy (Phase 4) lands
after the tool it references exists (skills-first applies to *behavior*
design — the design doc is that artifact — while the SKILL.md edit must name a
real tool); M3 reconciliation last (Phase 5) because it depends on the
persisted shape from Phase 3.

## #1 risk (watch for it during implementation)

The k-inference ladder (D2) silently disagreeing with M3's `_max_in_degree`
once a real model exists — producing an M1 number the M3 plan visibly
contradicts. Mitigations already in the design: same engine + same
`"medium"` convention (delta comes only from k), provenance
(`predictors_source`), the M1 message pre-committing to M3 refinement, and
the Phase-5 supersede sentence. Do not "improve" the ladder mid-implementation
without updating D2 and the tests together.
