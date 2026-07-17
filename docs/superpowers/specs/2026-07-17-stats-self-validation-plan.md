# Stats Self-Validation Layer — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-stats-self-validation-design.md` (read it first — check IDs, tolerances, finding schema, and integration points are all defined there)
**Executor notes:** All paths are relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–3 are pure functions in the `thesis-stats` submodule and land **before** any wiring. Do not reorder phases 4–8 ahead of 3.

**Submodule workflow reminder** (`libs/thesis-stats/README.md`, "Editing from a consumer"): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent repo to bump the pinned pointer. The submodule is installed editable (`requirements.txt` → `-e ./libs/thesis-stats`), so edits apply immediately without reinstalling.

---

## Phase 1 — thesis-stats: finding schema + claim shape + bounds/suspicious checks

Pure functions only. Everything in this phase lives in the submodule.

### Task 1.1 — Scaffold `validation.py` with `Finding` and the claim/metric registry
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (new), `libs/thesis-stats/tests/test_validation_bounds.py` (new)
- Write tests first: `Finding` construction round-trips to the design §5 dict shape; the metric registry contains the canonical ids (design §6.1); `validate_claims([])` returns `[]`.
- Implement: `Finding` (dataclass with `to_dict()`, or TypedDict — pick one, keep it JSON-serializable), `METRICS` registry, claim helper `make_claim(...)`, `_eps(claim)` implementing the display-precision epsilon (design §4.4: `0.5 × 10^-decimals`, defaults computed=4 / parsed=2), and an empty `validate_claims(claims) -> list[dict]` runner that dispatches to registered check functions.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_validation_bounds.py -q`
- **Done when:** schema tests pass; module imports with no engine/network/pandas dependency at import time.

### Task 1.2 — Bounds checks B1–B16 (incl. non-finite)
- **Files:** same two files.
- Tests first, parameterized per check id from design §4.1: in-range passes, out-of-range fires `hard` with correct `check`, `location`, `observed`, `tolerance`; the nuanced cases explicitly — negative α → `soft` (B3s), adjusted R² < 0 passes (B1), HTMT 1.03 → `soft` (B9s), VIF 0.8 → `hard` (B10), TLI 1.02 → `soft` (B14), NaN value → `hard bounds.non_finite` (§8). Rounding cases: parsed loading `1.00` at 2 dp passes, `1.01` fails.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_validation_bounds.py -q`
- **Done when:** all §4.1 rows have at least one pass + one fail test, green.

### Task 1.3 — Suspicious-pattern checks S1–S5
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py`, `libs/thesis-stats/tests/test_validation_suspect.py` (new)
- Tests: all-loadings ≥ 0.99 → one `soft suspect.all_loadings_high`; α = 0.985 → soft; R² = 0.96 → soft; four identical p values → soft; realistic mixed loadings (0.71–0.88) → zero findings.
- **Done when:** green; no suspect check ever emits `hard`.

## Phase 2 — thesis-stats: consistency + cross-table checks

### Task 2.1 — C3 t↔p and C4 CI containment (the arithmetic core)
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py`, `libs/thesis-stats/tests/test_validation_consistency.py` (new)
- Tests first: t=7.01/p=0.48 → `hard` (impossible at every df in the sweep); t=2.1/p=0.04 at df=200 → passes; t=2.1/p=0.06 stated df=30 → passes (possible), stated df=1000 → `soft`; p-string `"<0.001"` with t=7 passes, with t=1.2 → `hard`; CI [0.10, 0.30] with β=0.55 → `hard consistency.ci_contains`; CI [0.30, 0.10] → `hard` (ordering); β=0.345 vs CI [0.34, 0.35] at 2 dp → passes (half-ulp slack). Use `scipy.stats.t.sf` (already a pinned engine dependency).
- **Done when:** green, including the tolerance suite (design §9.3 cases for C3/C4).

### Task 2.2 — C1 AVE↔loadings, C2 CR↔loadings, C5 Fornell-Larcker diagonal, C7 f²↔R²
- **Files:** same.
- Tests: construct with loadings [.8,.8,.8] and AVE .64 passes; AVE .80 with those loadings → `hard consistency.ave_loadings`; partial loading set (flagged incomplete) → check skipped; CR recompute mismatch 0.04 (computed) → no finding, 0.09 → `soft`; F-L diagonal .802 with AVE .64 passes (tol .01), .75 → `hard`; f² implying impossible excluded-R² → `soft`.
- **Done when:** green; C1/C5 hard, C2/C7 soft, exactly per design §4.2.

### Task 2.3 — X1 n-consistency, X3 family mixing, X4 path↔construct, C6 flag contradiction
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py`, `libs/thesis-stats/tests/test_validation_xtable.py` (new)
- Tests: one table claiming n=234 and n=210 → `hard`; different tables n=234/n=228 → `soft`; AVE+HTMT claims together with CFI+RMSEA claims → `hard xtable.family_mix`; path `A -> B` with no construct B in measurement claims → `soft`; row flagged `significant: true` with p=0.21 → `hard consistency.flag_p`.
- **Done when:** green. (X2 hypothesis coverage is dothesis-context and lands in Task 4.2, not here.)

## Phase 3 — thesis-stats: native adapters + golden validation + release

### Task 3.1 — `claims_from_pls / spss_basic / spss_regression / rigor` + `claims_from_table` + `validate_result`
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py`, `libs/thesis-stats/tests/test_validation_adapters.py` (new)
- Tests first, driven by the real shapes: feed the exact `raw_*` payload keys (`src/thesis_stats/smartpls.py` `analyze_bootstrapping` return, `spss.py` `efa_result`/`regression_result`, `rigor.py` `run_rigor` return) and assert claim counts/metrics/units; `claims_from_table` handles `{item,value}`, `{pair,value}`, `{item,values:[...]}` matrix rows, and named-column rows (`alpha`, `CR`, `AVE`, `beta`, `t`, `p`, `loading`, `htmt`, `threshold_met`, `significant`); unknown columns dropped silently; `decimals` inferred from value strings where present.
- Implement `validate_result(kind, payload, source="computed")` dispatch (`kind ∈ {"pls","spss_basic","spss_regression","rigor","table"}`).
- **Done when:** green.

### Task 3.2 — Golden pass + mutation catch over the engine's own outputs
- **Files:** `libs/thesis-stats/tests/test_validation_golden.py` (new)
- Tests: run `run_pls` / `run_spss_basic` / `run_spss_regression` / `run_rigor` on the existing golden inputs (reuse `libs/thesis-stats/tests/conftest.py` fixtures and `tests/golden/`) → `validate_result` yields **zero hard findings** for each; then for ~10 targeted mutations (design §9.2 list) assert exactly the expected check id fires.
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (whole submodule suite — proves no regression in the engine tests either)
- **Done when:** whole submodule suite green.

### Task 3.3 — Export, version, README, submodule commit + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (export `validate_result`, `validate_claims`, `claims_from_table`, `Finding`; bump `__version__ = "0.2.0"`), `libs/thesis-stats/README.md` (document the validation API under "What it computes").
- Steps (submodule workflow):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat: deterministic self-validation layer (validate_result, claim checks)" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump — commits with the parent-repo work of later phases, or as its own commit now).
- **Verify:** `python -c "from thesis_stats import validate_result, Finding; print('ok')"` from the repo root.
- **Done when:** import works from the parent repo; submodule remote has the commit; parent pointer staged.

## Phase 4 — dothesis adapters (`agent/stats_validation.py`)

### Task 4.1 — `claims_from_run_stats(op, summary)` + `validate_run_stats`
- **Files:** `agent/stats_validation.py` (new, pure — no LangChain/tool imports), `agent/tests/test_stats_validation.py` (new)
- Tests first against the real tool summary shapes (`agent/tools/stats.py` `_summarize_pls`, `_op_efa`, `_op_regression_full`, `_op_mediation`, `_op_moderation`, `_op_rigor`, and the basic `_op_regression`/`_op_corr`/`_op_cronbach` outputs): claims extracted with correct metrics/units; `ci95` pairs become CI claims tied to their path's beta (C4 must fire on a corrupted ci95); an unknown/malformed summary yields `[]`.
- `validate_run_stats` returns the aggregate wrapper (design §5) and **never raises** (wrap internally; on exception log + return `{"passed": True, "hard": 0, "soft": 0, "findings": [], "crashed": True}`).
- **Verify:** `python -m pytest agent/tests/test_stats_validation.py -q`
- **Done when:** green.

### Task 4.2 — `claims_from_analysis_results(block)` + `validate_analysis_results` + X2 coverage
- **Files:** same.
- Tests first: the M4 skill's sample block (`skills/dothesis-m4-analysis/SKILL.md` §"Steps 4–5" JSON) validates clean; corrupted copies fire the right checks (AVE↔loadings via `measurement_model`, t↔p via `hypothesis_tests[].numbers` with the `"<0.001"` p-string form, family mix by injecting `cfi` into a PLS block); the orchestrator `results: {step: StepResult}` dict shape delegates to `claims_from_table`; a plain-string `analysis_results` yields zero claims + the soft `unstructured` finding; `None`/list shapes don't crash.
- X2: `validate_analysis_results(block, m3_hypotheses=[...])` — every hypothesis id missing from `hypothesis_tests[].hypothesis` → one `soft xtable.hypothesis_coverage` finding; no hypotheses passed → check skipped.
- **Done when:** green.

## Phase 5 — wire the `run_stats` boundary + `check_thresholds`

### Task 5.1 — Attach validation to `run_stats` returns
- **Files:** `agent/tools/stats.py` (edit `run_stats`, after the `result = fn(...)` call), `agent/tests/test_stats_tool.py` (extend)
- Tests first: a clean `pls_sem` run on the existing fixture carries **no** `validation` key (bounded payload); monkeypatch an op to return an impossible payload (R²=1.4) → response JSON contains `validation.hard == 1` with `check == "bounds.r2"`; monkeypatch `agent.stats_validation.validate_run_stats` to raise → op result still returned, no `validation` key (fail-open, design §8).
- Import `agent.stats_validation` lazily inside `run_stats` (mirrors the existing lazy `thesis_stats` imports).
- **Verify:** `python -m pytest agent/tests/test_stats_tool.py -q`
- **Done when:** green, including the pre-existing tests untouched.

### Task 5.2 — Merge validator findings into `check_thresholds`
- **Files:** `agent/tools/stats.py` (edit `check_thresholds`), `agent/tests/test_stats_tool.py` (extend)
- Tests first: pasted loadings rows including `1.31` → findings contain both the threshold classification and `hard bounds.loading`; a `{pair, value}` HTMT row of `1.05` → existing hard threshold finding + `soft` B9s; rows of valid values → unchanged behavior (regression test on the existing all->0.9 heuristic); validator crash → threshold findings still returned.
- Preserve the tool's docstring contract: outputs remain findings/classifications only — update the docstring to state the verification-arithmetic distinction (design §3.2).
- **Done when:** green.

## Phase 6 — the commit gate

### Task 6.1 — Block hard findings at the M4 `commit_slice` boundary
- **Files:** `agent/tools/state_tools.py` (insert the M4 guard after the M3 conceptual-model guard, before `store.commit_slice`), `agent/tests/test_state_tools.py` (extend)
- Tests first (temp-dir `ProjectStateStore`, existing pattern in `agent/tests/test_state_tools.py`):
  1. M4 commit with a clean structured `analysis_results` → succeeds, no warnings key.
  2. M4 commit whose block contains t=7.01/p=0.48 → returns `{"error": "stats_validation_failed…", "findings": [...]}`, and the store's `analysis_results` is **unchanged** (assert via `store.load()`).
  3. M4 commit with only soft findings (all loadings .995) → succeeds; result JSON carries `stats_validation_warnings`.
  4. Non-M4 commits and M4 commits without `analysis_results` in `writes` → completely untouched behavior.
  5. Validator raises → commit succeeds with `stats_validation: "unavailable"` in the result.
  6. X2: commit missing a result for hypothesis `H3` (M3 slice pre-seeded) → soft warning, commit succeeds.
- Lazy import; read M3 hypotheses via `store.load()["contextStore"].get("hypotheses")` (the flat store shape — see the `set_defense_date` precedent comment in `agent/tools/state_tools.py`).
- **Verify:** `python -m pytest agent/tests/test_state_tools.py -q`
- **Done when:** all six scenarios green; the full agent suite (`python -m pytest agent/tests -q`) still green.

## Phase 7 — orchestrator step-parse path

### Task 7.1 — `StepResult.validation` field + `run_analysis_step` wiring
- **Files:** `orchestrator/schemas/m4.py` (add `validation: dict | None = None` to `StepResult`), `orchestrator/tools/m4_analysis.py` (edit `run_analysis_step`), `orchestrator/tests/` (extend the existing m4 tool/parser test module — locate with `grep -rl run_analysis_step orchestrator/tests`)
- Tests first: a SmartPLS paste that regex-parses cleanly gets `validation.passed == True` (or no findings); a paste with a path row `LS -> PI 0.34 7.01 0.48` → StepResult carries the `hard consistency.t_p` finding; old persisted StepResult dicts (no `validation` key) still validate under `M4Output`; `thesis_stats` import failure → StepResult returned without `validation` (fail-open, lazy import).
- Use `thesis_stats.validate_result("table", ...)` / `claims_from_table` directly — do **not** import `agent.*` from the orchestrator tool.
- **Verify:** `python -m pytest orchestrator/tests -q -k "m4 or analysis"`
- **Done when:** green; full orchestrator suite unaffected.

## Phase 8 — rubric dimension

### Task 8.1 — `stats_validity_dimension` in the rubric
- **Files:** `quality/rubric.py` (new dimension function + registration in `score_thesis`), `tests/test_quality_gate.py` (extend; fixtures in `quality/fixtures/`)
- Tests first: `quality/fixtures/good_pls_thesis.json` → `stats_validity` score 1.0, no findings; a corrupted copy (impossible t/p in `m4_analysis.analysis_results`) → hard finding present in the dimension **and** in the top-level `blocking` list; free-text `analysis_results` → soft `unstructured` finding, score 1.0-ish, no crash; missing `m4_analysis` entirely → dimension scores 1.0 with no findings.
- Lazy-import `agent.stats_validation` inside the dimension (the `preflight_dimension` pattern in `quality/rubric.py`); map findings to `{issue, fix, chapter: "results", severity}`; weight 0.15; scoring per design §7.5 (−0.5/hard, −0.1/soft, floor 0).
- **Verify:** `python -m pytest tests/test_quality_gate.py -q`
- **Done when:** green; `score_thesis` on both stock fixtures still returns a well-formed result (no weight-normalization breakage — `_weighted` normalizes, but assert `overall ∈ [0,1]`).

## Phase 9 — skill + docs + final verification

### Task 9.1 — M4 skill and invariants
- **Files:** `skills/dothesis-m4-analysis/SKILL.md` (extend "Output sanity" + add a short "Self-validation findings" subsection: automatic at run_stats/commit; hard-vs-soft contract; two-register narration; fix-the-source-never-retype rule), `AGENTS.md` (invariants table row: hard validation findings block `analysis_results` commits)
- **Done when:** skill text matches the shipped behavior exactly (tool names, key names, the `stats_validation_warnings` key) — read the final code before writing the text.

### Task 9.2 — Full verification + submodule pointer sanity
- **Verify, in order:**
  1. `python -m pytest libs/thesis-stats/tests -q`
  2. `python -m pytest agent/tests -q`
  3. `python -m pytest orchestrator/tests -q`
  4. `python -m pytest tests -q` (repo default suite per `pytest.ini`)
  5. `git submodule status` — the `libs/thesis-stats` SHA matches the pushed validation commit; `git status` shows the pointer bump staged/committed in the parent.
- **Done when:** all four suites green and the submodule pointer is committed in the parent alongside the wiring changes.

---

## Sequencing rationale (for the implementer)

- Phases 1–3 are the initiative's whole value and carry zero integration risk — land and release them first so fillform benefits even if wiring pauses.
- Phase 4 isolates every dothesis shape assumption in one pure, heavily-tested module; phases 5–8 are then each a ~10-line lazy-import wiring change with behavioral tests.
- The commit gate (phase 6) intentionally lands **after** the run_stats attach (phase 5): the agent starts *seeing* findings one phase before anything blocks, which is the advisory-first rollout the vision's principle 4 implies.
- Nothing here touches M5 rendering, prose reconciliation, or the hypothesis registry — that is initiative #6 and depends on this layer, not vice versa.
