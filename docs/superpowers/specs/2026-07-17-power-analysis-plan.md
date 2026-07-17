# Power Analysis Ops — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-power-analysis-design.md` (read it first — formulas, the statsmodels `FTestPowerF2` mandate, output shape, and all integration points are defined there)
**Executor notes:** All paths are relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–2 are pure functions in the `thesis-stats` submodule and land **before** any dothesis wiring. Do not reorder Phases 3–5 ahead of 2.

**Submodule workflow reminder** (`libs/thesis-stats/README.md`, "Editing from a consumer"): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent repo to bump the pinned pointer. The submodule is installed editable, so edits apply immediately without reinstalling. `statsmodels==0.14.5` is already pinned in `libs/thesis-stats/pyproject.toml:23` — add **no** new dependency.

**⚠ The one landmine (design §4.1):** use `statsmodels.stats.power.FTestPowerF2` (takes Cohen's **f²** directly, conventional `df_num`=k / `df_denom`=n−k−1, `nobs = df_denom + df_num + 1`). Do NOT use `FTestPower` — its df arguments are historically swapped relative to conventional naming and it takes f (√f²). The Task 1.1 known-value test (N=77) is the tripwire; if it fails with N wildly off, you used the wrong class or the wrong effect-size scale.

---

## Phase 1 — thesis-stats: pure power functions (`power.py`)

Everything in this phase lives in the submodule. No dothesis imports anywhere.

### Task 1.1 — Scaffold `power.py` + regression (all three modes)
- **Files:** `libs/thesis-stats/src/thesis_stats/power.py` (new), `libs/thesis-stats/tests/test_power.py` (new)
- Write tests first (design §9.1/§9.2 regression rows):
  - a-priori f²=.15, k=3, α=.05, power=.80 → `required_n == 77`;
  - post-hoc f²=.15, k=3, n=200 → `achieved_power > 0.99` (≈0.998);
  - sensitivity k=3, n=150 → `mdes["value"]` ≈ 0.0747 (±.001), `mdes["interpretation"] == "small-to-medium"` band text per design §4.1 (bands .02/.15/.35, mirroring `rigor.py:33-43` `_band` semantics);
  - errors: effect_size ≤ 0, α ∉ (0,1), power ≤ α, missing `predictors`, posthoc missing `n`, posthoc `n ≤ predictors+1` → `ValueError` with a plain message;
  - solver-nan path (e.g. absurd combo) → `ValueError("power solver did not converge...")`, never a nan in the payload;
  - determinism: two identical calls → identical dicts; `json.dumps(result)` succeeds.
- Implement: `power_regression(mode, effect_size, alpha, power, predictors, n)` returning the design §6 dict (only the active mode's result key present; `required_n = ceil(df_denom) + k + 1` with the 1e-9 ceil guard; floor `required_n ≥ k+2`); the named-effect-size resolver (`"small"/"medium"/"large"` → .02/.15/.35 for f², `None` → medium, resolution recorded in `inputs.effect_size_label`); the justification-sentence template for regression (design §6 example text); the `required_n > 100_000` caveat; catch `ConvergenceWarning`/nan from statsmodels and re-raise as ValueError.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_power.py -q`
- **Done when:** green; the module imports without touching pandas/sklearn (statsmodels + scipy + math only).

### Task 1.2 — t-test + correlation
- **Files:** same two files.
- Tests first (design §9.1 rows): ttest a-priori d=.5 two-sided → `per_group == 64`, `required_n == 128`; posthoc accepts either total `n` (split by `ratio`) or explicit `n1`/`n2`; negative d → |d| used with an `assumptions` note; named sizes d → .2/.5/.8. Correlation a-priori r=.30 → `required_n == 85`, with an `assumptions` entry naming the Fisher-z approximation (design §4.2 documents G*Power exact = 84); posthoc and sensitivity closed-forms round-trip (a-priori N fed back into posthoc → power ≥ .80); named sizes r → .1/.3/.5; `alternative="one-sided"` reduces required N.
- Implement `power_ttest` (via `TTestIndPower`) and `power_correlation` (closed-form Fisher-z, design §4.2 formulas — scipy.stats.norm only), each with its justification template and citations (`Cohen (1988)`; ttest also `Faul et al. (2009)`).
- **Done when:** green.

### Task 1.3 — PLS-SEM (inverse square root + 10× cross-check)
- **Files:** same two files.
- Tests first (Kock & Hadaya 2018 worked examples, design §4.4): β_min=.197, α=.05, power=.80 → `required_n == 160`; β_min=.146 → `required_n == 290`; the z-sum is computed from α/power one-tailed (assert the α=.05/power=.80 constant ≈ 2.4866, i.e. NOT hard-coded 2.486, and that α=.01 changes the answer); `predictors=4` → `cross_checks` contains the 10×-rule entry with `required_n == 40` and the Hair et al. citation, and the justification recommends `max(inverse_sqrt, ten_times)`; posthoc β_min=.197, n=160 → power ≈ .80 (±.01); sensitivity n=160 → MDES β ≈ .197 (±.002); named sizes β → .1/.2/.3 with the "replace with your smallest hypothesized path" assumptions note.
- Implement `power_pls_sem` per design §4.4 (one-tailed z-sum; `effect_size` is β_min; `cross_checks` list; Kock & Hadaya justification template).
- **Done when:** green, including both worked-example values exactly.

### Task 1.4 — `run_power` dispatcher + payload contract
- **Files:** same two files.
- Tests first: `run_power("regression", "apriori", ...)` delegates correctly for all 4 analyses × 3 modes (12 combos, parameterized — assert `analysis`/`mode` echo, exactly one of `required_n`/`achieved_power`/`mdes` present, `justification` non-empty, `citations` non-empty, `method` names the backend); unknown `analysis`/`mode` → ValueError listing the valid values; posthoc always carries the Hoenig & Heisey observed-power caveat in `caveats` (design §4.5); all payloads JSON-serializable with floats at 4 dp.
- Implement `run_power(analysis, mode="apriori", **params)` with the exact signature of design §5.
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_power.py -q`
- **Done when:** green.

## Phase 2 — thesis-stats: validation coverage + release

### Task 2.1 — `power`/`d` metrics, integer-n bound, `claims_from_power`
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit), `libs/thesis-stats/tests/test_validation_bounds.py` (extend), `libs/thesis-stats/tests/test_power.py` (extend with golden-clean cases)
- Tests first (design §7, §9.3): claim `power`=1.2 → hard `bounds.power`; `power`=0.85 → clean; claim `n`=76.5 with `flags={"integer": true}` → hard `bounds.n_integer` (and n=76.5 WITHOUT the flag → unchanged behavior — no new finding, regression-guard the existing `bounds.n` at `validation.py:195-197`); claim `d`=7 → soft; `d`=0.6 → clean. Adapter: `claims_from_power(result)` over real `run_power` outputs emits the achieved-power claim (posthoc), the required-n claim flagged integer (apriori), and the effect-size claim mapped per analysis (f2 / corr / d / beta for β_min); **all 12 clean combos → `validate_claims` yields zero findings** (golden-clean, mirroring `test_validation_golden.py`); a mutated payload (`required_n: -5`) fires `bounds.n`.
- Implement: add `"power"`, `"d"` to `METRICS` (`validation.py:24-29`); the two bounds branches in `_bounds`; `claims_from_power` next to `claims_from_rigor` (`validation.py:701`); register kind `"power"` in `validate_result` (`validation.py:815-830`).
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (whole submodule suite — proves no engine/validation regression)
- **Done when:** whole submodule suite green.

### Task 2.2 — Export, version, README, submodule commit + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (export `run_power` in the API + `__all__` at `__init__.py:38-53`; bump `__version__` to `"0.3.0"` at `:36`), `libs/thesis-stats/README.md` (add a "Power analysis" bullet under "What it computes"; move the power line OUT of "Roadmap (deferred)")
- Steps (submodule workflow):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat: power analysis (a-priori/post-hoc/sensitivity; regression, correlation, t-test, PLS-SEM inverse-sqrt)" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump — commits with the parent-repo work of later phases, or as its own commit now).
- **Verify:** `python -c "from thesis_stats import run_power; print(run_power('regression','apriori',effect_size='medium',predictors=3)['required_n'])"` from the repo root prints `77`.
- **Done when:** import works from the parent repo; submodule remote has the commit; parent pointer staged.

## Phase 3 — the `run_stats` op

### Task 3.1 — `_op_power` + whitelist entry + validation branch
- **Files:** `agent/tools/stats.py` (add `_op_power`, register `"power"` in `OPS` at `stats.py:260-274`, extend the `run_stats` docstring op list at `:335-361`), `agent/stats_validation.py` (add the `op == "power"` branch in `claims_from_run_stats` at `:57`, delegating to `thesis_stats.validation.claims_from_power`), `agent/tests/test_stats_tool.py` (extend), `agent/tests/test_stats_validation.py` (extend)
- Tests first:
  - `run_stats(op="power", file="", params={analysis, mode, ...})` → JSON with `op: "power"` and `required_n == 77` for the textbook case (a-priori ignores `file`);
  - posthoc with `n` omitted and a real fixture CSV → `n` defaults to the file's row count (design §6); posthoc with `n` omitted and `file=""` → the standard `{"error": ...}` JSON (ValueError path, `stats.py:369-375`);
  - bad params (unknown analysis) → `{"error": ...}` JSON, never a raise;
  - validation ride-along: monkeypatch `_op_power` to return `achieved_power: 1.4` → response carries `validation.hard == 1` with `check == "bounds.power"`; clean run → no `validation` key;
  - `claims_from_run_stats("power", summary)` unit tests: apriori/posthoc/sensitivity summaries → correct claims; malformed summary → `[]`.
- Implement `_op_power` per the thesis-stats-backed op pattern (`stats.py:194-200`): lazy `import thesis_stats`, pull `n` from `_load_df(file).shape[0]` only when mode ≠ apriori and `n` is absent and `file` is a real path, call `ts.run_power(...)`, return the dict verbatim (it is already bounded).
- **Verify:** `python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q`
- **Done when:** green, pre-existing tests untouched. (The M4 commit gate at `agent/tools/state_tools.py:117` needs NO change — hard power findings flow through the existing `stats_validation_failed` path; add one gate test only if the suite lacks a power-shaped case after this task.)

## Phase 4 — M3 `sampling_plan` upgrade (power-primary, heuristic floor)

### Task 4.1 — Power-based plan + max-in-degree predictors + fail-open fallback
- **Files:** `agent/tools/instrument.py` (edit `make_sampling_plan_tool`, `:141-211`), the test module currently covering `make_sampling_plan_tool` under `agent/tests/` (extend; create `agent/tests/test_sampling_plan.py` if none exists — check with `grep -rln make_sampling_plan_tool agent/tests/`)
- Tests first (temp-store pattern used by the existing store-bound tool tests):
  1. PLS methodology + a nodes/edges model → plan carries `power_analysis` (the `run_power` dict), `target_n == max(inverse_sqrt_n, heuristic_n)`, and `rationale` containing the justification sentence;
  2. **predictors = max in-degree**, not total edges: a model with 5 edges but max 3 arrows into any construct → the 10× cross-check uses 3 (fixes the `instrument.py:173` total-edge approximation per design §8.1);
  3. regression methodology → `analysis == "regression"`, predictors = arrows into the dependent construct;
  4. CB-SEM/AMOS methodology → heuristic-only plan (power deferred, design §2), no `power_analysis` key, unchanged `target_n` from `target_sample_n`;
  5. fail-open: monkeypatch `thesis_stats.run_power` to raise → today's heuristic-only plan returned + persisted, no exception escapes;
  6. backward compat: `target_n`, `method_rule`, `screening`, `timeline_weeks` keys all still present (consumers: `agent/preflight.py:32`, `agent/tools/defense.py:30`).
- Implement per design §8.1 (methodology→analysis mapping mirrors `agent/sampling.py:21-27`; keep `target_sample_n` as the floor; extend `rationale` with the cross-check + ~10-15% invalid-response buffer sentence).
- **Verify:** `python -m pytest agent/tests -q -k "sampling or instrument"`
- **Done when:** all six scenarios green; full `agent/tests` still green.

## Phase 5 — preflight, rubric ride-along, defense, skills

### Task 5.1 — Preflight item upgrade + rubric ride-along test
- **Files:** `agent/preflight.py` (edit `preflight_check`, `:27-42`), the preflight tests (`grep -rln preflight_check agent/tests quality` to locate; extend), one rubric test asserting the ride-along (`quality/` test module for `preflight_dimension`, `quality/rubric.py:111-127`)
- Tests first: no `sample_plan.target_n` → the updated "run sampling_plan" message; `target_n` present but no `power_analysis` → the new "not power-justified" item; `target_n` + `power_analysis` present → neither item; both flat and nested `m3_design` store shapes (`preflight.py:20-24`); rubric: a store with an un-power-justified plan scores lower on the `preflight` dimension than one with `power_analysis` (zero rubric code changes expected — the test proves the ride-along).
- **Verify:** `python -m pytest agent/tests quality -q -k "preflight or rubric"` (adjust the path to wherever the rubric tests live: `grep -rln preflight_dimension --include="test_*.py" .`)
- **Done when:** green; `preflight_check` remains pure and advisory (no imports added beyond stdlib).

### Task 5.2 — Defense model-answer hint upgrade
- **Files:** `agent/tools/defense.py` (edit `_state_weakpoints`, `:29-36`), its test module (`grep -rln _state_weakpoints agent/tests/`)
- Tests first: `sample_plan` with `power_analysis` and n < 200 → the small-n question's `model_answer_hint` contains the computed justification sentence; n below the computed `required_n` → hint names the shortfall as the limitation to disclose; no `power_analysis` → existing generic hint unchanged.
- **Done when:** green; pure function, no store/tool changes.

### Task 5.3 — Skill + docstring copy
- **Files:** `skills/dothesis-m4-analysis/SKILL.md` (op list `:42-66`: add `power` with params + the three modes + the post-hoc observed-power caveat rule; interpretation guidance: seed limitations from post-hoc/sensitivity when achieved n < planned n), `skills/dothesis-m3-design/SKILL.md` (`:109-110` sample-size logic step → "call `sampling_plan`; quote its justification sentence"; `:149` quality bar wording), `agent/tools/stats.py` `run_stats` docstring (already edited in Task 3.1 — re-verify copy matches the skill)
- No test files — but run the full suites as the phase gate.
- **Verify:** `python -m pytest agent/tests -q && python -m pytest libs/thesis-stats/tests -q` (both fully green); `grep -n "power" skills/dothesis-m4-analysis/SKILL.md` shows the op documented.
- **Done when:** suites green; M3/M4 skills and the `run_stats` docstring agree on the op contract; parent-repo commit includes the `libs/thesis-stats` pointer bump from Task 2.2 (verify with `git submodule status libs/thesis-stats` — the SHA must match the pushed submodule commit).

---

## Execution order & gates

1. Phase 1 → 2 entirely inside the submodule; **push the submodule before any parent-repo wiring** (Phase 3 imports `run_power`).
2. Phase 3 before 4 (sampling_plan tests may reuse the op fixtures).
3. Phase 5 last — it documents what already works.
4. Final gate: both full suites green + the Task 2.2 one-liner prints `77` + `git submodule status` clean.

**Known-value anchors (do not weaken, same rule as the accuracy suites — `libs/thesis-stats/README.md` "Trust anchor"):** N=77 (regression textbook), 64/group (t-test), 85 (correlation Fisher-z), 160 and 290 (Kock & Hadaya), 0.998 (post-hoc), 0.0747 (MDES). All verified against the pinned statsmodels 0.14.5 on 2026-07-17 (design §9).
