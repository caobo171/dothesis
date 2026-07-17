# Data Screening & Preparation Ops — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-data-screening-design.md` (read it first — check formulas, the Little's-MCAR EM recipe, the op/apply contract, payload shapes, and all integration points are defined there)
**Executor notes:** All paths are relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–2 are pure functions in the `thesis-stats` submodule and land **before** any dothesis wiring. Do not reorder Phases 3–5 ahead of 2.

**Submodule workflow reminder** (`libs/thesis-stats/README.md:62-64`): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent repo to bump the pinned pointer. The submodule is installed editable, so edits apply immediately. **No new dependency** — pandas/numpy/scipy are pinned (`libs/thesis-stats/pyproject.toml:20-27`); statsmodels is NOT used here (it has no Little's MCAR test — verified, design §4.1).

**⚠ The one landmine (design §4.1, risk §10.1):** Little's MCAR test must use **EM (ML) estimates** of μ and Σ, not available-case estimates — available-case moments make the χ² statistic wrong in exactly the MAR cases the test exists to catch. And any numerical trouble (non-convergence, singular pattern covariance, n ≤ vars + 5) must yield `status: "skipped"` with a reason, **never** a computed-anyway p-value. The MCAR-vs-MNAR discrimination tests in Task 1.2 are the tripwire.

---

## Phase 1 — thesis-stats: pure screening functions (`screening.py`)

Everything in this phase lives in the submodule. No dothesis imports anywhere. All fixtures seeded (`numpy.random.default_rng(42)`), built by one shared helper.

### Task 1.1 — Fixture builder + missingness profile
- **Files:** `libs/thesis-stats/src/thesis_stats/screening.py` (new), `libs/thesis-stats/tests/test_screening.py` (new; put a `make_survey(...)` seeded builder at the top or in `tests/conftest.py` — 200×12 Likert 1–5, 3 constructs of 4 items, plus one continuous `age` column and a `gender` group column, with injectors for MCAR/MNAR holes, outlier rows, constant rows, and a negated item)
- Tests first (design §9.1 rows 1, §9.2): exact per-variable `missing_n`/`missing_pct` for 37 punched cells; `overall_missing_pct`, `n_complete_cases`, `n_patterns` exact; `out_of_range` counts when a value 9 is planted with `likert_min=1, likert_max=5`; inferred Likert bounds carry `"source": "inferred"` + a warning; `group="gender"` adds per-group n/missingness; fully-missing rows dropped and counted; empty data / `likert_min >= likert_max` → `ValueError`; determinism + `json.dumps` round-trip.
- Implement: module scaffold (DataLike coercion + numeric/measurement column scoping mirroring `rigor.py:20-30,158-168`), the missingness profile, range-violation rider, Likert inference.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_screening.py -q`
- **Done when:** green; module imports with pandas/numpy/scipy only (no statsmodels, no sklearn).

### Task 1.2 — Little's MCAR test (EM)
- **Files:** same two files.
- Tests first (design §9.1 rows 2–5, §10.1):
  - MCAR fixture (seeded random mask) → `p >= 0.05`; capture the exact χ²/df/p once and pin them (golden values — determinism guard);
  - MNAR fixture (delete top-quartile values of one item) → `p < 0.001`;
  - hand-built 2-pattern frame → `df == (Σ p_j) − p` hand-computed;
  - EM sanity: on the MCAR fixture, EM μ̂ within ±0.1 of the pre-hole column means;
  - no missing data → `status: "not_applicable"`; single missing-pattern → skipped (df = 0); duplicate column (singular Σ) → `status: "skipped"` with reason; n ≤ vars + 5 → skipped; >50 scoped columns → test runs on measurement items only, disclosed.
- Implement per design §4.1: pattern partition, EM for MVN (available-case init, conditional-expectation E-step per pattern, M-step, tol 1e-5, max 200 iters), the d² statistic over patterns, χ² p-value, the guard ladder. Output `mcar: {chi2, df, p, n_patterns, method, interpretation}` or `{status, reason}`.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_screening.py -q`
- **Done when:** green, including both discrimination tests (MCAR retained, MNAR rejected).

### Task 1.3 — Outliers (univariate z/IQR + Mahalanobis)
- **Files:** same two files.
- Tests first (design §9.1 rows 6–7, §9.2): 4 planted ~8-SD rows → exactly those positional indices flagged; `max_d2` equals a manual numpy `(x−x̄)ᵀ S⁻¹ (x−x̄)` computation; cutoff equals `scipy.stats.chi2.ppf(0.999, k)`; `d2 <= (n−1)²/n` holds; complete-cases-only with `excluded_incomplete_n` reported; univariate: one planted 10-SD `age` value flagged by both z (≥3.29) and extreme IQR fence, counts exact; singular S (duplicate column) → pinv + warning; `n <= k+1` → skipped with reason; flagged lists capped at 50 with `truncated: true` (build a 60-outlier frame); `thresholds={"mahalanobis_alpha": 0.005}` moves the cutoff.
- Implement per design §4.2. Row identity = 0-based positional index; never return row contents.
- **Done when:** green.

### Task 1.4 — Careless + reverse-coded audit
- **Files:** same two files.
- Tests first (design §9.1 rows 8–12): 7 planted constant rows → `flagged_n == 7`, exact indices, longstring == item count for them, `p95`/`max` reported; < 3 items → skipped; declared reverse item (negated: 6−x) → `r_it < 0` → in `needs_recoding` with the formula string; a normal item declared reverse → `appears_already_recoded`, and `apply_screening` does NOT recode it; auto-detect (no `reverse_items`) → the negated item in `suspected_reverse_keyed` (`r_it ≤ −0.10`), clean items absent; recode math: value v → `likert_min + likert_max − v` exactly (1→5, 2→4 … on 1–5).
- Implement per design §4.3–4.4: intra-individual SD (default threshold 0.05), longstring, corrected item-total correlation, declared/auto-detect modes.
- **Done when:** green.

### Task 1.5 — Recommendation engine + narrative + `run_screening` / `apply_screening`
- **Files:** same two files.
- Tests first (design §4.5, §9.1 rows 13–15, §5):
  - recommendation matrix, parameterized over the §4.5 table (no-missing → `none`; <5% + MCAR retained → `listwise`; MCAR rejected → `fiml_or_multiple_imputation`; MCAR skipped → threshold-only, disclosed; a >15% variable → per-variable drop flag); `citations` non-empty on every branch;
  - `run_screening` dispatcher: `checks=None` runs all applicable; unknown check name → `ValueError`; skipped checks land in `warnings` never raise (the `rigor.py:173-237` posture); payload matches the §5 top-level shape, floats 4 dp;
  - `apply_screening`: fixed order recode → careless → outliers → missing; `n_after == n_before − careless − outliers − listwise_dropped` per-stage exact; `missing: "mean"` fills the right cells (`imputed_cells` exact) and drops none; `missing: "regression"` → `ValueError` (not appliable in v1, design §2); idempotence: applying twice recodes once;
  - narrative: report-only run contains every count + the MCAR p in present/"recommended" register; `narrative_applied` (from an applied summary) uses past tense with n before/after; a skipped MCAR contributes its skip sentence.
- Implement per design §4.5 + §5 (deterministic sentence templates — compose only from computed fields, mirror `power.py:237-265` `_justify` style).
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_screening.py -q`
- **Done when:** green; `run_screening`/`apply_screening` are the only public entry points the module exports.

## Phase 2 — thesis-stats: validation coverage + release

### Task 2.1 — `missing_pct`/`mahalanobis_d2` metrics, screening count-consistency, `claims_from_screening`
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit), `libs/thesis-stats/tests/test_validation_bounds.py` (extend), `libs/thesis-stats/tests/test_validation_consistency.py` (extend), `libs/thesis-stats/tests/test_screening.py` (extend with golden-clean)
- Tests first (design §7, §9.3): claim `missing_pct`=180 → hard `bounds.missing_pct`; =3.2 → clean; `mahalanobis_d2`=−2 → hard; d² above `(n−1)²/n` (claim carries n) → hard; screening n-claims with role flags where `n_after ≠ n_before − Σ removed` → hard `consistency.screening_counts`; `removed > n_before` → hard; reconciling counts → clean. Adapter: `claims_from_screening` over real `run_screening` output emits per-variable `missing_pct`, MCAR `p` (`is_p` flag) + `df`, `max_d2` with n, and the role-flagged count claims (plus applied-run accounting claims); **golden-clean: clean-fixture report-only AND applied outputs → `validate_claims` yields zero findings** (mirrors `tests/test_validation_golden.py`); a mutated payload (`n_after` bumped by 1) fires the consistency check. Register kind `"screening"` in `validate_result` (`validation.py:851-868`) and cover the dispatch.
- Implement: add the two metrics to `METRICS` (`validation.py:24-30`); the bounds branches in `_bounds` (`validation.py:110-212`); the `consistency.screening_counts` check in the consistency family (`validation.py:298-302`); `claims_from_screening` next to `claims_from_rigor` (`validation.py:712-728`).
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (whole submodule suite — proves no engine/validation regression)
- **Done when:** whole submodule suite green.

### Task 2.2 — Export, version, README, submodule commit + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (export `run_screening`, `apply_screening` in the imports + `__all__` at `__init__.py:23-55`; bump `__version__` `"0.3.0"` → `"0.4.0"` at `:36`), `libs/thesis-stats/README.md` (add a "Data screening" bullet under "What it computes"; delete the missing-data line from "Roadmap (deferred)" at `:89-92`)
- Steps (submodule workflow):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat: data screening (missingness + Little's MCAR (EM), z/IQR + Mahalanobis outliers, careless/straight-lining, reverse-coding audit, cleaning narrative)" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump — commits with the parent-repo work of later phases, or as its own commit now).
- **Verify:** from the repo root, `python -c "from thesis_stats import run_screening; import numpy as np; print(sorted(run_screening([{'a':1,'b':2},{'a':2,'b':None}]).keys()))"` prints the payload keys including `missing` and `narrative`.
- **Done when:** import works from the parent repo; submodule remote has the commit; parent pointer staged (`git submodule status libs/thesis-stats` shows the pushed SHA).

## Phase 3 — the `run_stats` op

### Task 3.1 — `_op_screening` + whitelist entry + apply/derived-file + validation branch
- **Files:** `agent/tools/stats.py` (add `_op_screening`, register `"screening"` in `OPS` at `stats.py:277-293`, extend the `run_stats` docstring op list at `:352-386` with the design §6 entry), `agent/stats_validation.py` (add the `op == "screening"` branch in `claims_from_run_stats` at `:55-87`, delegating to `thesis_stats.validation.claims_from_screening` — mirror the `power` branch at `:84-86`), `agent/tests/test_stats_tool.py` (extend), `agent/tests/test_stats_validation.py` (extend)
- Tests first (design §6, §9.4; use tmp_path fixture CSVs):
  - report-only: `run_stats(op="screening", file=csv, params={measurement, likert_min, likert_max})` → JSON with `op: "screening"`, the §5 payload keys, **no `applied` key, and no `_screened.csv` written** (the no-silent-mutation tripwire, risk §10.2);
  - apply: `params.apply={recode_reverse: true, drop_careless: true, drop_outliers: true, missing: "listwise"}` → `<stem>_screened.csv` exists next to the source, its row count equals `applied.n_after`, recoded column round-trips (spot-check one recoded cell = min+max−original), payload carries `narrative_applied`; re-running apply is idempotent (same n_after, item not double-recoded);
  - `.sav`/`.xlsx` inputs still produce a CSV derivative (via `_load_df`, `stats.py:21-32`) — cover with the xlsx path at least;
  - bad params (unknown check, `missing: "regression"` in apply) → `{"error": ...}` JSON, never a raise (`stats.py:393-399`);
  - bounded: a 60-outlier frame → flagged list length ≤ 50, `truncated: true`;
  - validation ride-along: monkeypatch `_op_screening` to return `missing_pct: 180` in the per-variable table → response carries `validation.hard >= 1` with check `bounds.missing_pct`; clean run → no `validation` key (`stats.py:400-411` needs NO change);
  - `claims_from_run_stats("screening", summary)` unit tests: real payload → expected claims; malformed → `[]`.
- Implement `_op_screening` per the thesis-stats-backed pattern (`stats.py:248-256`): lazy import, `_load_df`, `ts.run_screening(...)`, on `apply` build the plan from the run's own flagged sets (`needs_recoding` only — never `appears_already_recoded`), `ts.apply_screening(...)`, write `<stem>_screened.csv`, merge `applied` + `narrative_applied`, return through `_round_floats` (`stats.py:130-137`).
- **Verify:** `python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q`
- **Done when:** green, pre-existing tests untouched.

## Phase 4 — persisted block, commit gate, preflight

### Task 4.1 — `data_screening` block coverage in the commit gate
- **Files:** `agent/stats_validation.py` (add the `data_screening` branch in `claims_from_analysis_results` at `:202-280` — emit the §8.2 block's claims: overall/per-check counts with role flags, MCAR p, treated as `source="parsed"` like the rest of the function `:276-280`), `agent/tests/test_stats_validation.py` (extend), `agent/tests/test_state_tools.py` (extend)
- Tests first: a clean §8.2-shaped `data_screening` block → zero findings; `missing.overall_pct: 180` → hard; `n_after` that doesn't reconcile with `n_before` minus the removed counts → hard `consistency.screening_counts`; gate test: `commit_slice("M4", {"analysis_results": {..., "data_screening": <hard-bad block>}})` → `stats_validation_failed` JSON (the existing path, `agent/tools/state_tools.py:105-127` — NO gate code change expected); a soft-only block commits with `stats_validation_warnings`.
- **Verify:** `python -m pytest agent/tests/test_stats_validation.py agent/tests/test_state_tools.py -q`
- **Done when:** green with zero changes inside `state_tools.py`.

### Task 4.2 — Preflight message upgrade
- **Files:** `agent/preflight.py` (edit the `missing_data_plan` message at `:40-41` per design §8.3), the tests covering `preflight_check` (locate: `grep -rln preflight_check agent/tests quality`)
- Tests first: no `missing_data_plan` → the new message naming `run_stats op=screening`; plan present → no item; both flat and nested `m3_design` store shapes (`preflight.py:20-24`); the reverse-coded item's wording unchanged (`preflight.py:36-37`).
- **Verify:** `python -m pytest agent/tests -q -k preflight`
- **Done when:** green; `preflight_check` stays pure/advisory (no new imports).

## Phase 5 — skills + final gate

### Task 5.1 — M4/M5 skill copy
- **Files:** `skills/dothesis-m4-analysis/SKILL.md` (op list `:42-71`: add the `screening` entry per design §6; pipeline `:85-92`: insert step 1.5 with the report-first / confirm-before-apply / use-`applied.derived_file`-downstream rules per design §8.1; results-block section `:130-152`: add the `data_screening` block shape per design §8.2 and note `descriptives.n` = post-screening n; "What you do NOT do" `:232-237`: add the no-unconfirmed-apply rule), `skills/dothesis-m5-writing/SKILL.md` (one rule: Chapter 3 quotes `analysis_results.data_screening.narrative` verbatim), `agent/tools/stats.py` `run_stats` docstring (already edited in Task 3.1 — re-verify the copy matches the skill)
- No new test files — the phase gate is the full suites.
- **Verify:** `python -m pytest agent/tests -q && python -m pytest libs/thesis-stats/tests -q` (both fully green); `grep -n "screening" skills/dothesis-m4-analysis/SKILL.md` shows the op, step 1.5, and the data_screening block documented.
- **Done when:** suites green; skill, docstring, and design §6 agree on the op contract; the parent-repo commit includes the `libs/thesis-stats` pointer bump from Task 2.2 (`git submodule status libs/thesis-stats` SHA matches the pushed submodule commit).

---

## Execution order & gates

1. Phase 1 → 2 entirely inside the submodule; **push the submodule before any parent-repo wiring** (Phase 3 imports `run_screening`).
2. Phase 3 before 4 (the gate/persisted-block tests reuse the op fixtures).
3. Phase 5 last — it documents what already works.
4. Final gate: both full suites green + the Task 2.2 one-liner works from the repo root + `git submodule status` clean + the report-only tripwire test (no file written without `apply`) present and green.

**Anchors (do not weaken — same rule as the accuracy suites, `libs/thesis-stats/README.md:74-87`):** the MCAR/MNAR discrimination pair, the hand-computed Little's df, the manual-numpy Mahalanobis parity, the exact planted-defect counts (4 outliers / 7 straight-liners / 37 holes), the recode round-trip (v → min+max−v), the apply n-accounting identity, and golden-clean (clean data → zero validation findings). If the MCAR golden χ²/p drifts after a refactor, that is a bug in the EM, not a tolerance to loosen.
