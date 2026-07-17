# PLS-SEM Completeness (Q² / MGA+MICOM / IPMA) — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-pls-completeness-design.md` (read it FIRST — the exact algorithms in §4, the op contracts in §6, and the rng-consumption pin in §9.2 are normative; this plan only sequences them)
**Executor notes:** All paths relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 1–2 live entirely in the `libs/thesis-stats` submodule and land **before** any dothesis wiring. Do not reorder.

**Submodule workflow reminder** (`libs/thesis-stats/README.md:50-69`): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent to bump the pinned pointer. Installed editable — edits apply immediately. **No new dependencies** — numpy/pandas/scipy only, all pinned.

**Trust anchor** (`libs/thesis-stats/README.md:77-91`): every new statistic ships with an independent reference implementation in its test, the `tests/test_pls_accuracy.py` pattern. Never weaken an existing tolerance; never touch the golden files (`tests/golden/`) — design §3.3 makes Q² opt-in in `run_pls` precisely so `test_golden_parity.py:50-57` (strict key-set equality) stays green untouched.

**⚠ The one landmine (design §10.1):** blindfolding's observed and predicted values must both be in the **round-d engine's standardized metric** (design §4.1 step 3d). Write the Task 1.2 reference loop from the design's formula, NOT by reading your implementation. If the noise anchor (Q² ≤ 0 for a pure-noise endogenous block) fails while implementation and reference agree, you made the same metric mistake twice — reread §4.1 before touching tolerances.

**⚠ The second landmine (design §9.2):** the MICOM/MGA permutation loop consumes exactly **one `rng.permutation(n)` per draw and nothing else** from the rng. The seeded-reference test depends on this contract; any extra rng call breaks exact-match and the fix is to remove the call, never to loosen the test.

---

## Phase 1 — thesis-stats: pure engine functions + independent-reference tests

Everything in this phase is inside the submodule. No dothesis imports anywhere.

### Task 1.1 — Scaffold `pls_advanced.py`: `engine_spec` lift + fixtures
- **Files:** `libs/thesis-stats/src/thesis_stats/pls_advanced.py` (new),
  `libs/thesis-stats/src/thesis_stats/smartpls.py` (edit `_engine_spec` only),
  `libs/thesis-stats/tests/conftest.py` (extend),
  `libs/thesis-stats/tests/test_pls_advanced_spec.py` (new)
- Tests first: `engine_spec(model, df)` on the conftest model
  (`tests/conftest.py:25-50`) returns exactly the `(CONSTRUCT_ITEMS, STRUCTURE)`
  of `tests/conftest.py:13-22`; missing-column and no-questions errors match
  the current messages (`smartpls.py:229-232`); a moderation model
  (reuse/extend the fixture from `tests/test_pls_moderation.py`) still routes
  through the analyzer unchanged.
- Implement: move the body of `SmartPLSAnalyzer._engine_spec`
  (`smartpls.py:222-247`) to module-level `engine_spec(model, df)` in
  `pls_advanced.py`; make the method a one-line delegate. Add to conftest: a
  deterministic `make_group_labels(n=300, seed=7)` helper (balanced two-level
  Series) and a `make_group_shifted_records(beta_xy=...)` generator variant
  (parameterizing the 0.55 coefficient in `tests/conftest.py:55-57`) for MGA's
  planted-difference test.
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (full suite — the
  lift must be inert; `test_golden_parity.py` is the tripwire)
- **Done when:** full submodule suite green with zero golden-file diffs.

### Task 1.2 — Q² blindfolding (`q2_blindfold`)
- **Files:** `libs/thesis-stats/src/thesis_stats/pls_advanced.py`,
  `libs/thesis-stats/tests/test_pls_q2.py` (new)
- Tests first (design §9.1):
  - independent reference: naive-loop blindfolding written from design §4.1
    (explicit round/cell loops, mean-imputation on raw columns, fresh
    `PLSEngine` per round, `x̂ = λ_j·Σβ_p·score_p`, both sides standardized
    with the round engine's block mean/sd) → per-endogenous-construct Q²
    matches `q2_blindfold` within 1e-9;
  - noise anchor: Z-indicators replaced with `rng.normal` noise → `q2["Z"] ≤ 0`;
  - signal anchor: standard fixture → `q2["Y"] > 0` and
    `q2["Y"] < r2["Y"] + 0.05` (r2 from `run_pls`'s `raw_inner_summary`);
  - guards: `(n·k) % D == 0` (n=300, k=3, D=6 → 900 divisible) → `DataError`
    whose message suggests another D; `D < 2` and `D ≥ n` → `DataError`; D=7
    on the fixture → fine;
  - only endogenous constructs appear in `q2` (X absent);
  - `interpretation` bands: 0.02/0.15/0.35 (mirror `power.py:44` `_band`
    semantics);
  - determinism: two calls → identical dicts; `json.dumps(result)` succeeds.
- Implement `q2_blindfold(df, construct_items, structure, *, omission_distance=7,
  include_q2_effects=False)` per design §4.1 and §5 (diagonal groups
  `(i+j) mod D`; full refit per round; redundancy prediction; SSE/SSO
  accumulation; the payload shape of design §5).
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_pls_q2.py -q`
- **Done when:** green, including the noise anchor (the landmine tripwire).

### Task 1.3 — q² effect sizes
- **Files:** same two files.
- Tests first: `include_q2_effects=True` on the fixture → `q2_effects` has one
  entry per structural path into each endogenous construct
  (`X -> Y`, `X -> Z`, `Y -> Z`); each value matches the reference loop rerun
  with that predictor dropped from `structure` (1e-9); dropping the only
  predictor of Y yields the empty-structure Q²_excl … assert it computes (an
  endogenous construct with no remaining predictors has structural prediction
  ŷ=0 — the design's formula degrades gracefully); default (`False`) →
  `q2_effects is None`.
- Implement per design §4.1 (q² = (Q²_incl − Q²_excl)/(1 − Q²_incl), same D,
  same groups).
- **Done when:** green.

### Task 1.4 — MICOM (`run_micom`)
- **Files:** `libs/thesis-stats/src/thesis_stats/pls_advanced.py`,
  `libs/thesis-stats/tests/test_pls_mga.py` (new)
- Tests first (design §9.2):
  - seeded reference: `seed=42, n_permutations=200` — the test re-implements
    the permutation loop from the design (one `default_rng(42).permutation(n)`
    per draw, per-group `PLSEngine` fits, `c_k` on pooled standardized blocks,
    add-one-smoothed p) and matches `c`, `p`, mean/variance stats **exactly**;
  - null calibration: `make_group_labels` (independent of data) → all `c > 0.99`,
    step-2 passed for all constructs, `invariance_level` ∈ {"full", "partial"};
  - non-invariance: group B with Y's indicators scrambled/re-keyed →
    compositional fails for Y, `invariance_level == "none"` reported per
    design's per-construct verdicts;
  - per-group fit failure (constant indicator within one group) → `DataError`
    naming group and column;
  - determinism: same seed twice → identical payloads.
- Implement `run_micom(df, construct_items, structure, groups, *,
  n_permutations=1000, seed=42, alpha=0.05)` per design §4.2 — one rng, one
  permutation loop recording c/mean/logvar stats per draw, failed replicates
  skipped and counted (design §10.3).
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_pls_mga.py -q`
- **Done when:** green, exact seeded match included.

### Task 1.5 — MGA (`run_mga_permutation`)
- **Files:** same two files.
- Tests first (design §9.2/§9.3 of the design):
  - seeded reference for `diff` and `p_permutation` (shares the Task 1.4
    reference loop — MGA stats recorded from the same draws);
  - null: independent labels → all `p_permutation > 0.05`, every path
    `defensible: true`, `comparison_defensible: true`;
  - planted difference: group B from `make_group_shifted_records`
    (β(X→Y) shifted 0.55→0.15) → `p_permutation < 0.05` for `X -> Y`; other
    paths > 0.05;
  - gating: with the Task 1.4 non-invariant group B → Y-paths
    `defensible: false`, `comparison_defensible: false`, `message` populated,
    per-group betas still present (soft refusal, design §4.3);
  - `diff == beta_group_a − beta_group_b` to 1e-12 for every path;
  - `micom=None` computes MICOM internally in the same loop (assert the
    combined payload equals composing Task 1.4's output);
  - replicate-drop accounting: monkeypatched engine failure on some
    permutations → those draws skipped, `>5%` drops → soft note in payload.
- Implement per design §4.3 + the guard set of design §6.2's pure-layer half
  (two-level requirement, n floors) — the group-column guards that need the
  raw column live in the `run_mga` wrapper (Task 1.7).
- **Done when:** green.

### Task 1.6 — IPMA (`ipma`)
- **Files:** `libs/thesis-stats/src/thesis_stats/pls_advanced.py`,
  `libs/thesis-stats/tests/test_pls_ipma.py` (new)
- Tests first (design §9.3):
  - hand-computed micro-fixture: 2 constructs, equal known weights, Likert 1–5,
    one all-3s indicator column → its rescaled mean is exactly 50.0; construct
    performance equals the hand-computed convex combination to 1e-9;
  - reference importance: test-side sklearn `LinearRegression` (the
    `test_pls_accuracy.py:14` import pattern) on the test's own rescaled
    composites, total effects by explicit path enumeration → matches
    `importance` within 1e-6 on the 3-construct fixture with `target="Z"`;
  - properties: every `performance` and `target_performance` ∈ [0, 100];
    `rows` covers exactly the constructs with |total effect on target| > 1e-9;
    `mean_importance`/`mean_performance` are the row means;
  - guards: negated indicator column → hard error whose message names the
    screening op's reverse-coded audit; `target="X"` (exogenous) and
    `target="Nope"` → `ModelSpecError`; omitted scale bounds → inferred
    per-indicator min/max used and `scale.inferred == true`;
  - `interpretation` sentence contains the importance value and both construct
    names (design §6.3 example).
- Implement `ipma(df, construct_items, structure, target, *, scale_min=None,
  scale_max=None)` per design §4.4 (normalized positive weights → 0–100
  composites; unstandardized structural OLS on rescaled composites mirroring
  `pls_engine.py:117-135` without z-scoring; total-effect accumulation
  mirroring `pls_engine.py:203-221`).
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_pls_ipma.py -q`
- **Done when:** green.

### Task 1.7 — Public wrappers: `run_mga`, `run_ipma`, `run_pls` q2 kwarg
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (edit),
  `libs/thesis-stats/src/thesis_stats/smartpls.py` (edit),
  `libs/thesis-stats/tests/test_api.py` (extend),
  `libs/thesis-stats/tests/test_pls_q2.py` / `test_pls_mga.py` /
  `test_pls_ipma.py` (extend)
- Tests first:
  - `run_pls(model, data)` (no kwarg) → payload key-set **unchanged** (assert
    `"raw_q2" not in result`); `run_pls(..., q2_omission_distance=7)` →
    `raw_q2` present with the design §5 shape; moderation model +
    `q2_omission_distance=7` → `raw_q2` is `{"q2": None, "note": ...}` per
    design §4.1;
  - `run_mga(model, data, group="grp")` end-to-end on records that include the
    group column: group column excluded from indicators, MICOM+MGA payload of
    design §6.2 (pure-layer keys); guards: missing group column, constant
    column, 3 levels without `group_values` (message lists levels), 3 levels
    with `group_values=[a,b]` → works, either group n<20 → `DataError`, n<30 →
    soft finding key, moderation model → `ModelSpecError`;
  - `run_ipma(model, data, target="Z")` end-to-end; moderation model →
    `ModelSpecError`;
  - dict-model coercion + typed-error re-wrapping match `run_pls`'s behavior
    (`__init__.py:128-140`);
  - `test_golden_parity.py` untouched and green.
- Implement: wrappers per design §5; `_run_pls_single_stage`
  (`smartpls.py:249-265`) computes `q2_blindfold` when the kwarg is set and
  threads it through `_extract_pls_metrics` (`smartpls.py:424-507`) as
  `raw_q2`; `_run_pls_with_moderation` (`smartpls.py:267-282`) sets the
  skip-note payload.
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (whole suite)
- **Done when:** whole suite green; `raw_q2` absent by default.

## Phase 2 — thesis-stats: validation coverage + release

### Task 2.1 — Bounds + consistency checks for the new metrics
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit),
  `libs/thesis-stats/tests/test_validation_bounds.py` (extend),
  `libs/thesis-stats/tests/test_validation_consistency.py` (extend)
- Tests first (design §7):
  - `q2=1.2` → hard `bounds.q2`; `q2=-0.4` and `q2=0.31` → clean;
  - `micom_c=1.3` → hard; `micom_c=-0.2` → soft; `micom_c=0.98` → clean;
  - `ipma_performance=130` → hard `bounds.ipma_performance`; `=-3` → hard;
    `=63.2` → clean;
  - consistency: same-construct claims `q2=0.9, r2=0.4` → soft
    `consistency.q2_r2`; `q2=0.31, r2=0.56` → clean;
  - MGA diff: claims `beta[group A]=0.41, beta[group B]=0.22, diff=0.30` →
    hard `consistency.mga_diff`; `diff=0.19` → clean;
  - family mix: `q2` + `cfi` claims → `xtable.family_mix` fires (extends the
    `validation.py:504-509` test row).
- Implement: `micom_c`, `ipma_performance` added to `METRICS`
  (`validation.py:24-30`; `q2` already there at `:28`); the bounds branches in
  `_bounds` (`:110-218`); the two consistency checks beside `_c_construct` /
  `_c_path` (`:311-409`); `"q2"` added to `_PLS_FAMILY` (`:476`).
- **Verify:** `python -m pytest libs/thesis-stats/tests -q`
- **Done when:** whole suite green (no regressions in existing validation tests).

### Task 2.2 — Claims adapters + golden-clean
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit),
  `libs/thesis-stats/tests/test_validation_adapters.py` (extend),
  `libs/thesis-stats/tests/test_validation_golden.py` (extend)
- Tests first (design §7, §9.4):
  - `claims_from_pls` on a `run_pls(..., q2_omission_distance=7)` payload emits
    one `q2` claim per endogenous construct (table `structural_model`);
  - `claims_from_mga(run_mga(...))` emits per-path group betas (paths suffixed
    `[group A]`/`[group B]` in `unit.path`), permutation `p` claims flagged
    `is_p`, per-construct `micom_c` + `p`, and the beta/diff triple for
    `consistency.mga_diff`;
  - `claims_from_ipma(run_ipma(...))` emits `ipma_performance` per row +
    target;
  - **golden-clean:** all three real outputs on the clean fixture →
    `validate_claims` returns `[]`; mutated copies (`performance: 130`,
    `c: 1.3`, `q2: 1.2`, diff≠βa−βb) each fire exactly the named check;
  - `validate_result("mga", ...)` / `validate_result("ipma", ...)` dispatch
    (`validation.py:878-897`); malformed payloads → `[]`, never a raise.
- Implement adapters beside `claims_from_pls` (`validation.py:569-650`);
  register the kinds in `validate_result`.
- **Verify:** `python -m pytest libs/thesis-stats/tests -q`
- **Done when:** green, golden-clean rows included.

### Task 2.3 — Export, version, README, submodule commit + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (add `run_mga`,
  `run_ipma` to imports + `__all__` at `:40-58`; bump `__version__` `"0.4.0"` →
  `"0.5.0"` at `:38`), `libs/thesis-stats/README.md` (extend the PLS-SEM bullet
  in "What it computes" `:9-11` with Q²/MGA+MICOM/IPMA; add
  `tests/test_pls_q2.py`, `test_pls_mga.py`, `test_pls_ipma.py` to the trust-
  anchor suite list `:83-86`)
- Steps (submodule workflow, `README.md:67-69`):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat: PLS-SEM completeness — Q2 blindfolding, MGA+MICOM (seeded permutation), IPMA" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump; commits with the
     parent-repo work of Phase 3, or as its own commit now).
- **Verify:** from the repo root:
  `python -c "import thesis_stats as ts; print(sorted(k for k in ts.__all__ if k.startswith('run_')))"`
  lists `run_ipma` and `run_mga`; `python -m pytest libs/thesis-stats/tests -q`
  green; `git -C libs/thesis-stats status` clean and pushed.
- **Done when:** import works from the parent repo; submodule remote has the
  commit; parent pointer staged.

## Phase 3 — the `run_stats` ops (dothesis side)

### Task 3.1 — `pls_sem` gains Q²; summarizer + validation extension
- **Files:** `agent/tools/stats.py` (edit `_op_pls_sem` `:194-200` and
  `_summarize_pls` `:151-191`), `agent/stats_validation.py` (edit
  `_pls_summary_claims` `:93-143`), `agent/tests/test_stats_tool.py` (extend),
  `agent/tests/test_stats_validation.py` (extend)
- Tests first:
  - `run_stats(op="pls_sem", ...)` on the fixture CSV → response has the
    design §6.1 `q2` block (`omission_distance: 7`, per-endogenous `values` +
    `interpretation`); `params={"q2": false}` → no `q2` key;
    `params={"omission_distance": 8}` → echoed;
  - a dataset/D combo where `(n·k) % D == 0` → the op's standard
    `{"error": ...}` JSON (`stats.py:432-437`), never a raise;
  - `_pls_summary_claims` picks up `q2.values` → `q2` claims; monkeypatched
    summary with `q2.values: {"Z": 1.4}` → response `validation.hard ≥ 1` with
    check `bounds.q2` (ride-along path `stats.py:440-448`);
  - existing pls_sem tests untouched and green.
- Implement per design §6.1 (default on, `q2_omission_distance=7` through
  `ts.run_pls`).
- **Verify:** `python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q`
- **Done when:** green.

### Task 3.2 — `_op_mga` + whitelist + validation branch
- **Files:** `agent/tools/stats.py` (add `_op_mga`, register `"mga"` in `OPS`
  `:310-326`, extend the `run_stats` docstring `:386-424`),
  `agent/stats_validation.py` (add `op == "mga"` branch in
  `claims_from_run_stats` `:55-90`, delegating to
  `thesis_stats.validation.claims_from_mga` — the `power`/`screening` lazy-
  import pattern at `:84-89`), `agent/tests/test_stats_tool.py`,
  `agent/tests/test_stats_validation.py` (extend)
- Tests first:
  - happy path on a fixture CSV with a group column → design §6.2 payload
    (groups/micom/paths/`comparison_defensible`/`seed` present);
  - `n_permutations` capped (mirror `_BOOTSTRAP_CAP` mechanics, `stats.py:127`
    — cap 2000 per design §6.2); default `seed=42` echoed; same call twice →
    byte-identical JSON (determinism, design §6.4);
  - missing `group` param, unknown column, 3-level column → `{"error": ...}`
    JSON with the level-listing message;
  - non-invariant fixture → `comparison_defensible: false` + `message`, and
    the response still carries per-group betas;
  - validation ride-along: monkeypatched payload with `c: 1.3` → hard
    `bounds.micom_c` in `validation.findings`.
- Implement `_op_mga(file, conceptual_model=None, measurement=None, group=None,
  group_values=None, n_permutations=1000, seed=42, alpha=0.05, **_)` per the
  thesis-stats-backed op pattern (`stats.py:194-200`): `_adapt` + `_records`,
  call `ts.run_mga`, return the payload (already bounded — no row-level data).
- **Verify:** `python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q`
- **Done when:** green; the M4 commit gate needs NO change (hard findings flow
  through `agent/tools/state_tools.py:98-126` as-is — add one gate-shaped test
  only if the suite lacks an MGA case).

### Task 3.3 — `_op_ipma` + whitelist + validation branch
- **Files:** same four files as Task 3.2.
- Tests first:
  - happy path `params={"target": "Z", "scale_min": 1, "scale_max": 5}` →
    design §6.3 payload (rows/crosshairs/`interpretation` sentence);
  - omitted bounds → `scale.inferred: true`;
  - missing `target`, exogenous target, reversed-item data → `{"error": ...}`
    JSON (reversed-item message names the screening op);
  - ride-along: monkeypatched `performance: 130` → hard
    `bounds.ipma_performance`;
  - `claims_from_run_stats("ipma", payload)` unit tests: well-formed → claims;
    malformed → `[]`.
- Implement `_op_ipma(file, conceptual_model=None, measurement=None,
  target=None, scale_min=None, scale_max=None, **_)`; register `"ipma"`.
- **Verify:** `python -m pytest agent/tests -q`
- **Done when:** full agent suite green.

## Phase 4 — skill copy + final gates

### Task 4.1 — M4 skill + docstring copy
- **Files:** `skills/dothesis-m4-analysis/SKILL.md` (op list under "The tool"
  `:40`: extend the `pls_sem` bullet `:51` with Q²; add `mga` + `ipma` bullets
  with params, the MICOM-gating rule, and the IPMA reverse-item/screening
  rule — design §8.1 wording; reporting rules near `:161-168`: Q² thresholds
  0.02/0.15/0.35 and ">0 = predictive relevance" beside the existing
  metric-family rule `:36`/`:162`), `agent/tools/stats.py` `run_stats`
  docstring (re-verify the Task 3.2/3.3 copy matches the skill exactly)
- No new test files — the phase gate is the suites.
- **Verify:** `grep -n "mga\|ipma\|Q²" skills/dothesis-m4-analysis/SKILL.md`
  shows all three documented;
  `python -m pytest agent/tests -q && python -m pytest libs/thesis-stats/tests -q`
  both fully green.
- **Done when:** suites green; skill, docstring, and design §6 agree on every
  param name; the sample `structural_model.q2` block (`SKILL.md:156`) is now
  satisfiable by computed values.

### Task 4.2 — Final gate
- `git submodule status libs/thesis-stats` — SHA matches the pushed Phase 2.3
  commit; parent commit includes the pointer bump.
- `python -c "import json, thesis_stats as ts; from tests... "` — not needed;
  instead run the one-liner smoke from the repo root:
  `python -m pytest libs/thesis-stats/tests/test_pls_q2.py libs/thesis-stats/tests/test_pls_mga.py libs/thesis-stats/tests/test_pls_ipma.py -q`
- Determinism spot-check: run the `mga` op twice on the same fixture → identical
  JSON bytes.
- Golden files: `git -C libs/thesis-stats diff --stat tests/golden/` is empty.

---

## Execution order & gates

1. Phase 1 → 2 entirely inside the submodule; **push the submodule before any
   parent-repo wiring** (Phase 3 imports `run_mga`/`run_ipma`).
2. Task 1.1 (spec lift) before everything — all later tasks consume
   `engine_spec`. Task 1.4 before 1.5 (MGA shares MICOM's permutation loop).
3. Phase 3 tasks are independent of each other after 3.1; keep the docstring
   edits cumulative.
4. Phase 4 last — it documents what already works.

**Known anchors (do not weaken — same rule as the accuracy suites,
`libs/thesis-stats/README.md:88`):** noise-block Q² ≤ 0; signal Q²(Y) ∈ (0,
R²+0.05); D=6/n=300/k=3 rejected; seeded MICOM/MGA exact-match at
n_permutations=200/seed=42; null-labels p > 0.05 and c > 0.99; planted-shift
`X -> Y` p < 0.05; all-3s Likert column → performance 50.0 exactly; every
performance ∈ [0,100]; `raw_q2` absent from default `run_pls` output (golden
parity).
