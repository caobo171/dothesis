# PLS-SEM Completeness (Q² / MGA+MICOM / IPMA) — Design Spec

**Date:** 2026-07-17
**Status:** Ready for implementation planning
**Roadmap:** initiative #8, `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:250-276`
**Companion plan:** `docs/superpowers/specs/2026-07-17-pls-completeness-plan.md`
**Depends on:** #1 stats self-validation (SHIPPED — `libs/thesis-stats/src/thesis_stats/validation.py`, `agent/stats_validation.py`)
**All paths repo-relative to the dothesis root.**

---

## 1. Motivation

The M4 skill already promises Q² to students: the metric-family rule names
"PLS-SEM → R²/f²/Q²" (`skills/dothesis-m4-analysis/SKILL.md:36`, `:162`) and the
sample persisted block carries `"structural_model": {"r2": ..., "q2": {"PI": 0.31}}`
(`SKILL.md:156`). But the engine cannot compute Q² — grep-verified, no
blindfolding / MGA / invariance / IPMA anywhere in `libs/thesis-stats`
(roadmap `:255-256`). The validation layer even reserved the metric name
already: `"q2"` sits in `METRICS` (`validation.py:28`) and in the parsed-table
column map (`validation.py:753`) with **no bounds branch and no producer** —
today a student can only get a Q² by pasting one.

Committee reality (roadmap `:256-259`): Vietnamese/ASEAN business faculties
routinely require Q²; any thesis comparing groups (gender, region, cohort)
needs MGA gated by MICOM to be defensible; IPMA is the standard "practical
implications" figure that feeds Chapter 5.

The compute rail exists (roadmap `:19-22`): add pure functions to the
submodule, whitelist ops in `agent/tools/stats.py`, teach the M4 skill. This
spec extends the hand-rolled `PLSEngine`
(`libs/thesis-stats/src/thesis_stats/pls_engine.py:13`) — Mode A, path
weighting, dominant-positive orientation — which is the estimator everything
below builds on. Advances the "unbeatable on PLS-SEM" position (roadmap `:275-276`).

## 2. Scope and non-scope

**In scope (v1):**

- **Q²** cross-validated **redundancy** via blindfolding, per endogenous
  construct, omission distance D (default 7), computed alongside `run_pls`.
  Optional **q² effect sizes** (predictor-omission reruns).
- **MICOM** (Henseler, Ringle & Sarstedt 2016): step 1 configural (procedural
  assert), step 2 compositional invariance (permutation test on the
  correlation *c* of composites built with each group's weights), step 3
  equality of composite means and variances (permutation). Partial invariance
  (step 2 passes) unlocks path comparison; full invariance unlocks pooled-data
  analysis claims.
- **MGA**: two-group **permutation test** on path-coefficient differences
  (Chin & Dibbern 2010), gated by MICOM. Soft-refusal semantics per roadmap
  `:264-265`: when invariance fails, per-group paths are still returned but the
  comparison is marked not defensible.
- **IPMA** (Ringle & Sarstedt 2016): total effects (importance) × rescaled
  0–100 construct scores (performance) toward one target construct, with the
  same-scale/same-direction guards.
- Self-validation coverage (bounds + claims adapters) for every new number.
- `run_stats` wiring: Q² rides on `pls_sem`; new `mga` and `ipma` ops.
- M4 skill copy.

**Out of scope (deferred, recorded here so nobody "helpfully" adds them):**

- Henseler's **parametric** MGA (Welch–Satterthwaite on per-group bootstrap
  SEs). It needs 2× full bootstraps (2×1000 engine refits) and adds a second
  p-value that can disagree with the permutation p. The permutation test is
  assumption-free, shares machinery with MICOM, and is what Hair et al.
  recommend as first choice. The output schema keeps a `method` field so the
  parametric variant can be added later without breaking shape.
- MGA with **>2 groups** (v1 errors and tells the user to run pairwise) and
  MGA/IPMA/Q² on **moderation (two-stage) models** — the two-stage refit per
  permutation/omission round (`smartpls.py:284-350`) is a cost/complexity
  multiplier; v1 raises `ModelSpecError` with a plain message for `mga`/`ipma`
  and returns `q2: null` + a note for moderated `pls_sem`.
- PLSpredict (out-of-sample indicator-level prediction). Blindfolding Q² is
  what the region's committees ask for by name.
- CB-SEM anything (roadmap #9).
- **No new dependencies.** Everything below is numpy/pandas/scipy — all pinned
  (`libs/thesis-stats/pyproject.toml`; README pin rationale `README.md:71-75`).

## 3. Placement and op-shape decision

### 3.1 Engine placement: one new submodule module

New module `libs/thesis-stats/src/thesis_stats/pls_advanced.py` holding three
pure sections (blindfolding, MICOM+MGA, IPMA). Rationale:

- `pls_engine.py` stays the verbatim-ported estimator (its docstring promises
  the class body is unchanged from fillform; `pls_engine.py:3-5`) — do not grow
  it.
- `smartpls.py` is the analyzer/orchestration layer; it will *call*
  `pls_advanced.q2_blindfold(...)` from `_run_pls_single_stage`
  (`smartpls.py:249-265`) where `(df, construct_items, structure)` are already
  in scope, and attach the result via `_extract_pls_metrics`
  (`smartpls.py:424-507`).
- MGA and IPMA get public wrappers `run_mga` / `run_ipma` in
  `src/thesis_stats/__init__.py` mirroring `run_pls` (`__init__.py:128`):
  coerce `AdvanceModel`, `_check_measurement(strict=True)`, delegate.
- The model→`(construct_items, structure)` derivation currently lives as
  `SmartPLSAnalyzer._engine_spec` (`smartpls.py:222-247`). Lift its body to a
  module-level `engine_spec(model, df)` in `pls_advanced.py` (or a tiny
  `_spec.py`) and make the method a one-line delegate — golden parity
  (`tests/test_golden_parity.py`) proves the refactor is inert.

### 3.2 Op shape: `q2` on `pls_sem`; `mga` and `ipma` as new ops

This is the shape the roadmap already prescribes ("`pls_sem` gains Q² …; new
`mga` op …; new `ipma` op", roadmap `:261-267`), and it is the right one:

- **Q² is a structural-model column, not a separate analysis.** Committees read
  it in the same table as R² (the skill's sample block puts `q2` beside `r2`,
  `SKILL.md:156`). It needs no new user input beyond an optional omission
  distance, and it is cheap (D≈7 engine refits per endogenous construct — the
  full accuracy fixture fits in milliseconds). So: computed by default inside
  the `pls_sem` op, tunable via `params.omission_distance`.
- **MGA needs a `group` column and MICOM gating semantics** — a different
  contract, a different table, and a refusal path. Separate op.
- **IPMA needs a `target` construct and scale bounds** — again a different
  contract with its own guards. Separate op.
- The whitelist is the security boundary (`agent/tools/stats.py:1-8`); each op
  stays a single vetted function with an inspectable parameter surface.

### 3.3 `run_pls` payload compatibility (fillform-shared)

`tests/test_golden_parity.py:50-57` asserts **strict key-set equality** against
golden payloads captured from pre-extraction fillform. Therefore `run_pls`
gains an **opt-in** kwarg:

```python
run_pls(model, data, bootstrap_samples=1000, q2_omission_distance=None)
```

`None` (default) → payload byte-identical to today, goldens untouched, fillform
unaffected. An integer → payload gains `raw_q2` (additive key; golden tests
only run with the default). The dothesis `pls_sem` op passes
`q2_omission_distance=7` unless `params.omission_distance` overrides or
`params.q2 == false`. Do **not** recapture goldens to make Q² default-on — the
golden's contract is "identical to fillform's analyzer output" (`README.md:86`).

## 4. Methods — exact algorithms

Notation: the engine standardizes each indicator block with ddof=1 z-scores
(`pls_engine.py:46-52`); LV scores are standardized composites
(`pls_engine.py:90-99`); structural coefficients are OLS on those scores
(`pls_engine.py:113-141`); total effects accumulate powers of the direct-effect
matrix (`pls_engine.py:203-221`).

### 4.1 Q² — blindfolding, cross-validated redundancy

Reference: Hair, Hult, Ringle & Sarstedt (2017), *A Primer on PLS-SEM* (2nd
ed.), ch. 6 (Stone 1974; Geisser 1974). Cross-validated **redundancy** is the
variant SmartPLS reports and the one usable as a structural-quality metric
(prediction of the endogenous block flows through the structural model).

For **each endogenous construct** T (a key of `structure` with non-empty
sources — same definition as `inner_summary`'s Endogenous type,
`pls_engine.py:184-185`), with indicator block columns `items = construct_items[T]`
(k = len(items), n rows):

1. **Omission groups.** Assign every cell (i, j) of the n×k raw indicator
   block to omission group `g = (i + j) mod D` — the classical diagonal
   pattern, so no round ever blanks a full row or full column when the guard
   below holds.
2. **Guard.** Require `2 ≤ D < n` and `(n * k) % D != 0` → else `DataError`
   with the message telling the user to pick another D (suggest D±1). Note:
   `(n·k) % D != 0` **implies** Hair et al.'s published rule "n / D must not be
   an integer" (if D | n then D | n·k), so the single stronger assert covers
   both. Default D = 7 (Hair et al.'s recommendation, range 5–12).
3. **Per round d = 0..D-1:**
   a. Copy the raw dataframe; set the group-d cells of T's block to NaN, then
      impute each blanked cell with the **column mean of the remaining
      (non-omitted) rows of that raw column** (SmartPLS mean-replacement).
   b. Refit `PLSEngine(imputed_df, construct_items, structure)` — full
      re-estimation: weights, scores, paths all recomputed without the omitted
      information. This is the "how blindfolding re-estimates" contract: it is
      a *full refit on mean-imputed data*, not a frozen-weights projection.
   c. **Predict the omitted cells** (redundancy prediction, standardized
      metric of the round's engine): for omitted cell (i, j),
      `x̂_ij = λ_j^(d) · ŷ_T,i^(d)` where
      `ŷ_T,i^(d) = Σ_p β_p^(d) · score_p,i^(d)` is the structural prediction
      of T's score from its predecessors' scores (round-d engine's
      `path_coefficients()` row T, `pls_engine.py:148`), and `λ_j^(d)` is the
      round-d loading of item j (`engine.loadings[T][j]`, `pls_engine.py:107-111`).
   d. Accumulate, **in the same standardized metric**: the observed value is
      the round-d engine's standardized value of the *true* raw cell —
      i.e. z-standardize the true raw x_ij with the round-d block mean/sd
      (`engine.X` uses the imputed matrix; the true cell must be transformed
      with the identical mean/sd used in that round). Then
      `SSE += (x_std − x̂)²` and `SSO += x_std²` (the trivial prediction in a
      standardized metric is the mean, 0).
4. **Q²(T) = 1 − SSE/SSO** over all D rounds and all k items of T.

**Metric-consistency rule (the #1 correctness risk, see §10):** observed and
predicted values MUST be in the same standardization. The design fixes it as
"round-d engine's standardized metric" and the reference test recomputes the
whole loop independently; the property anchors in §9.1 (noise → Q² ≤ 0) catch
a same-mistake-twice scale error.

Range: Q² ∈ (−∞, 1]; Q² > 0 = the model has predictive relevance for T;
effect-size bands 0.02 / 0.15 / 0.35 (small/medium/large, Hair et al. 2017) —
band text mirrors `power.py:44` `_band`.

**q² effect sizes (optional, `include_q2_effects=True`):**
`q²(P→T) = (Q²_incl − Q²_excl) / (1 − Q²_incl)`, where Q²_excl reruns the full
blindfolding with predictor P removed from `structure[T]` (same D, same
groups). Cost: D × (#predecessors) extra refits per endogenous construct —
still cheap, but off by default in the op to keep `pls_sem` latency flat;
same bands as f².

Moderated models: v1 returns `q2: null` with
`note: "Q² not computed for moderation models (two-stage) — deferred"` (see §2).

### 4.2 MICOM — measurement invariance of composite models

Reference: Henseler, Ringle & Sarstedt (2016), "Testing measurement invariance
of composites using partial least squares", *International Marketing Review*
33(3). Three steps; all randomness from one `numpy.random.default_rng(seed)`.

Inputs: full df, `(construct_items, structure)`, a `group` Series with exactly
two levels A/B (guards §6.2), `n_permutations` (default 1000, cap 2000),
`seed` (default 42), `alpha` (default 0.05).

- **Step 1 — configural invariance (procedural).** Same indicators, same
  structural model, same estimation settings for both groups by construction:
  both groups are fit with the *same* `(construct_items, structure)` through
  the *same* `PLSEngine` defaults. Emit `configural: true` with the checked
  facts (identical spec, both fits converged). If either per-group fit raises
  (e.g. zero-variance indicator inside a group), that is a hard `DataError`
  naming the group and column.
- **Step 2 — compositional invariance.** For each construct k:
  `c_k = corr( X_pooled_std @ w_k^(A),  X_pooled_std @ w_k^(B) )`, where
  `w_k^(g)` are the outer weights from the engine fitted on group g alone and
  `X_pooled_std` is the pooled standardized block. The engine's
  dominant-positive orientation (`pls_engine.py:88-97`) keeps both weight
  vectors consistently signed — this is exactly why the hand-rolled engine is
  safe for MICOM where plspm's broken sign correction would not be
  (`pls_engine.py:18-22`).
  Permutation distribution: for each of `n_permutations` draws, randomly
  reassign rows to two groups of the original sizes (permute the group
  labels), refit both engines, recompute `c_k^perm`. One-sided p-value:
  `p_k = (1 + #{c_perm ≤ c_observed}) / (1 + n_permutations)` (add-one
  smoothing → never exactly 0). **Invariance holds for k iff p_k ≥ alpha**
  (observed c is NOT significantly below the permutation distribution).
- **Step 3 — equality of means and variances.** Using pooled-weights composite
  scores (engine fit on pooled data): for each construct,
  `d_mean = mean_A − mean_B` and `d_logvar = log(var_A / var_B)`; compare each
  against its permutation distribution (same draws as step 2 — one rng, one
  loop, all three statistics recorded per draw); two-sided
  `p = (1 + #{|stat_perm| ≥ |stat_obs|}) / (1 + n_permutations)`. Both
  non-significant → **full** invariance; step 2 only → **partial** invariance
  (sufficient for MGA on path coefficients); step 2 failed for any construct →
  **no** invariance for that construct.

Output verdict per construct: `configural / compositional {c, p, passed} /
means {diff, p, passed} / variances {log_ratio, p, passed}` and an overall
`invariance_level: "full" | "partial" | "none"`.

### 4.3 MGA — permutation test on path differences

Same rng, same permutation draws as MICOM (one loop computes everything —
determinism and half the compute). For every structural path s→t present in
the pooled model (nonzero cell of `path_coefficients()`, matching the
summarizer's path enumeration `agent/tools/stats.py:155-165`):

- Observed: `Δ = β^(A)_{s→t} − β^(B)_{s→t}` from the two per-group engines.
- Permutation two-sided p: `p = (1 + #{|Δ_perm| ≥ |Δ|}) / (1 + n_permutations)`.
- Report per path: `beta_group_a, beta_group_b, diff, p_permutation,
  defensible` where `defensible = (invariance_level != "none" for BOTH s and
  t)`. Non-defensible paths keep their numbers but the op-level
  `comparison_defensible: false` + `message` implements the roadmap's
  soft-refusal (`:264-265`): the agent may show group betas, but must not
  narrate "the difference is significant" — skill copy enforces the wording,
  the claims adapter marks it (§7).

Why permutation and not parametric first: no distributional assumption on β,
no per-group bootstrap cost, one shared machinery with MICOM, and Hair et
al. (2018, *Advanced Issues*) recommend it. `method: "permutation"` is encoded
in the output for future parametric addition.

### 4.4 IPMA — importance–performance map

Reference: Ringle & Sarstedt (2016), "Gain more insight from your PLS-SEM
results: the importance–performance map analysis", *IMDS* 116(9).

Inputs: df, spec, `target` construct (must be endogenous), `scale_min`/
`scale_max` (theoretical indicator bounds; default: inferred per-indicator
observed min/max **with a soft warning** — inference understates performance
spread when nobody used a scale endpoint).

1. **Guards (hard):** target exists and is endogenous; every construct with a
   nonzero total effect on target has all-positive outer weights — a negative
   weight/loading means a reversed indicator, and the rescaled composite would
   be meaningless. Error message points at the `screening` op's reverse-coded
   audit (`agent/tools/stats.py:277-306`) — recode first, rerun. All indicators
   of the involved constructs must share one scale (single scale_min/scale_max
   pair in v1; mixed-scale → hard error naming the offending columns).
2. **Rescale indicators:** `x' = 100 · (x − scale_min) / (scale_max − scale_min)`.
3. **Performance scores:** per involved construct k, normalize the engine's
   outer weights to sum to 1: `w̃ = w_k / Σ_j w_k,j` (weights from the pooled
   engine, `pls_engine.py:101-105`, all positive per guard). Case-level
   rescaled composite `s_k(i) = Σ_j w̃_j · x'_ij ∈ [0, 100]` (convex
   combination of values in [0,100] — the bound is structural, and §7 validates
   it). `performance_k = mean_i s_k(i)`.
4. **Importance:** *unstandardized* total effects in the rescaled metric —
   re-run the structural OLS regressions on the **rescaled composite scores
   without standardizing** (same target→sources layout as
   `pls_engine.py:117-135`, minus the z-scoring), then accumulate total
   effects with the same matrix-power scheme as `effects()`
   (`pls_engine.py:203-221`). `importance_k` = total effect of k on target.
   Interpretation: "+1 point of k's performance (0–100 scale) → +importance_k
   points of target's performance, ceteris paribus" — this is the sentence the
   skill will template for Chapter 5.
5. **Output:** rows for every construct with |total effect| > 1e-9 on target:
   `{construct, importance, performance}`, plus `target_performance`,
   `mean_importance`, `mean_performance` (the quadrant crosshairs for the M5
   chart), and the scale bounds used.

## 5. Pure API (`libs/thesis-stats/src/thesis_stats/pls_advanced.py`)

```python
def engine_spec(model: AdvanceModel, df: pd.DataFrame) -> tuple[dict, dict]
    # lifted body of SmartPLSAnalyzer._engine_spec (smartpls.py:222-247)

def q2_blindfold(df, construct_items, structure, *, omission_distance: int = 7,
                 include_q2_effects: bool = False) -> dict
    # {"q2": {construct: float}, "omission_distance": 7,
    #  "interpretation": {construct: "small|medium|large|none"},
    #  "q2_effects": {"P -> T": float, ...} | None}

def run_micom(df, construct_items, structure, groups: pd.Series, *,
              n_permutations: int = 1000, seed: int = 42, alpha: float = 0.05) -> dict

def run_mga_permutation(df, construct_items, structure, groups: pd.Series, *,
                        n_permutations: int = 1000, seed: int = 42,
                        alpha: float = 0.05, micom: dict | None = None) -> dict
    # computes MICOM itself when micom is None (single shared permutation loop)

def ipma(df, construct_items, structure, target: str, *,
         scale_min: float | None = None, scale_max: float | None = None) -> dict
```

Public wrappers in `src/thesis_stats/__init__.py` (exports + `__all__` at
`__init__.py:40-58`; `__version__` 0.4.0 → 0.5.0 at `:38`):

```python
run_mga(model, data, group: str, *, group_values=None, n_permutations=1000,
        seed=42, alpha=0.05) -> dict          # MICOM + MGA in one payload
run_ipma(model, data, target: str, *, scale_min=None, scale_max=None) -> dict
run_pls(model, data, bootstrap_samples=1000, q2_omission_distance=None) -> dict
```

`run_mga`/`run_ipma` follow `run_pls`'s pattern (`__init__.py:128-140`): coerce
via `_coerce_model`, `_check_measurement(strict=True)`, typed errors
(`ModelSpecError` for moderation nodes / unknown target; `DataError` for group
problems / D-divisor / mixed scales). The `group` column is popped from the
data before it can be mistaken for an indicator.

## 6. The `run_stats` op contract (`agent/tools/stats.py`)

### 6.1 `pls_sem` — Q² rides along

`_op_pls_sem` (`stats.py:194-200`) passes
`q2_omission_distance = params.omission_distance or 7` (and skips when
`params.q2 is False`). `_summarize_pls` (`stats.py:151-191`) gains one bounded
key:

```json
"q2": {"omission_distance": 7,
       "values": {"PI": 0.31}, "interpretation": {"PI": "medium"},
       "note": null}
```

(`note` carries the moderation-skip message when applicable; `values` is
per-endogenous-construct — same cardinality as `reliability`'s r_squared,
already bounded.)

### 6.2 New op `mga`

```
run_stats(op="mga", file=..., params={
  conceptual_model, measurement?,        # same adaptation path as pls_sem (stats.py:144-148)
  group: "gender",                       # REQUIRED — column in the data file
  group_values?: ["male","female"],      # optional pick when >2 levels exist
  n_permutations?: 1000,                 # capped like _BOOTSTRAP_CAP (stats.py:127)
  seed?: 42, alpha?: 0.05
})
```

Guards (in the pure layer, surfaced as the op's standard `{"error": ...}`
JSON, `stats.py:432-437`): missing/constant group column; ≠2 levels after
`group_values` selection (message lists the levels and says "run pairwise");
either group n < 20 → hard error; group n < 30 → soft finding in the payload;
moderation model → error.

Bounded output:

```json
{"groups": {"A": {"label": "male", "n": 152}, "B": {"label": "female", "n": 148}},
 "micom": {"configural": true,
           "constructs": {"LS": {"c": 0.998, "p": 0.41, "compositional": true,
                                 "mean_diff": {"value": 0.11, "p": 0.22, "equal": true},
                                 "var_logratio": {"value": -0.04, "p": 0.61, "equal": true}}},
           "invariance_level": "partial"},
 "paths": {"LS -> PI": {"beta_group_a": 0.41, "beta_group_b": 0.22,
                        "diff": 0.19, "p_permutation": 0.031, "defensible": true}},
 "comparison_defensible": true,
 "method": "permutation", "n_permutations": 1000, "seed": 42,
 "message": null}
```

When `invariance_level == "none"` for any construct on a path: that path gets
`defensible: false`; `comparison_defensible: false`;
`message`: "Compositional invariance failed for {constructs} — group path
differences are not interpretable. Report per-group models separately."

### 6.3 New op `ipma`

```
run_stats(op="ipma", file=..., params={
  conceptual_model, measurement?,
  target: "PI",                          # REQUIRED
  scale_min?: 1, scale_max?: 5
})
```

Bounded output:

```json
{"target": "PI", "target_performance": 63.2,
 "rows": [{"construct": "LS", "importance": 0.34, "performance": 71.5},
          {"construct": "TR", "importance": 0.18, "performance": 55.0}],
 "mean_importance": 0.26, "mean_performance": 63.3,
 "scale": {"min": 1, "max": 5, "inferred": false},
 "interpretation": "A one-point gain in LS performance (0-100) raises PI performance by 0.34 points."}
```

Both new ops register in `OPS` (`stats.py:310-326`) and in the `run_stats`
docstring op list (`stats.py:386-424`). The whitelist rule is unchanged: an op
not in the dict does not run.

### 6.4 Determinism

`seed` defaults to a constant (42) in both the pure layer and the op, so a
re-run reproduces the report byte-for-byte — vision principle 5
(`2026-07-17-dothesis-vertical-agent-vision.md:245`) and the roadmap's seed
plumbing note (`:406-411`). Note: the existing bootstrap is unseeded
(`smartpls.py:378` `df.sample` without `random_state`) — fixing that is
initiative #14's seed-plumbing work, not this spec's; the NEW code must not
repeat the mistake.

## 7. Self-validation integration

Everything computed must be checkable (roadmap #1 dependency, `:275`).

**Bounds** (`validation.py:_bounds`, `:110-218`):

- `q2` — already in `METRICS` (`validation.py:28`); add the branch:
  `q2 > 1 + eps` → hard `bounds.q2` (Q² ∈ (−∞, 1]); `q2 ≤ 0` is legitimate (no
  relevance) — never a bounds finding. New *consistency* check (soft)
  `consistency.q2_r2`: computed Q² > R² + 0.1 for the same construct is
  suspicious (redundancy Q² practically sits below R²).
- `micom_c` (new metric): |c| ≤ 1 hard (it is a correlation — reuse semantics
  of `bounds.corr`, `validation.py:151-153`); `c < 0` soft (composites
  anti-correlated across groups almost certainly means an orientation problem).
- `ipma_performance` (new metric): ∈ [0, 100] hard (mirrors
  `bounds.missing_pct`, `validation.py:203-205`).
- MICOM/MGA p-values reuse the existing `p` metric + `bounds.p`
  (`validation.py:154-156`) via `flags={"is_p": True}`.
- Per-group betas reuse `beta`; `diff` needs no bound (unbounded), but gets a
  consistency check: `consistency.mga_diff` hard —
  `|diff − (beta_a − beta_b)| > tol`.
- Add `"q2"` to `_PLS_FAMILY` (`validation.py:476`) so a pasted CB-SEM table
  mixing Q² with CFI/TLI trips `xtable.family_mix` (`validation.py:504-509`).

**Claims adapters** (`validation.py`, beside `claims_from_pls` `:569-650`):

- `claims_from_pls` extended: when the raw payload has `raw_q2`, emit
  `make_claim("q2", v, construct=c, table="structural_model")`.
- New `claims_from_mga(result)`: per path — `beta` ×2 (paths suffixed
  `[group A]`/`[group B]` in `unit.path` so the t↔p machinery doesn't
  cross-wire groups), `p` with `is_p` flag; per construct — `micom_c`, its
  `p`; plus the diff-consistency claims.
- New `claims_from_ipma(result)`: `ipma_performance` per row + target;
  importance is emitted as no metric (unbounded, unit-dependent) — coverage is
  the [0,100] performance bound and the hand-value reference test.
- Register kinds `"mga"`, `"ipma"` in `validate_result`
  (`validation.py:878-897`).

**Dothesis-side** (`agent/stats_validation.py`): `claims_from_run_stats`
(`:55-90`) gets `op == "mga"` / `op == "ipma"` branches delegating to the new
submodule adapters (the `power`/`screening` pattern, `:84-89`), and
`_pls_summary_claims` (`:93-143`) picks up the summarizer's `q2.values`. Hard
findings then flow through the existing ride-along (`stats.py:440-448`) and the
M4 commit gate (`agent/tools/state_tools.py:98-126`) with **zero gate changes**.

## 8. Product integration

### 8.1 M4 skill (`skills/dothesis-m4-analysis/SKILL.md`)

- Op list (under "The tool", `:40`): extend the `pls_sem` bullet (`:51`) with
  "…f², GoF, **Q² (blindfolding, D=7)**"; add `mga` and `ipma` bullets with
  their params and the two behavioral rules:
  - **MGA rule:** "MGA is valid ONLY after MICOM. If the op returns
    `comparison_defensible: false`, report the per-group models but state
    plainly that the groups cannot be compared — never narrate a difference
    from a non-invariant model."
  - **IPMA rule:** "IPMA needs same-scale, positively-keyed indicators — if
    the op errors on reversed items, run `screening`'s reverse-coded audit and
    recode first. Quote the `interpretation` sentence in Chapter 5."
- Reporting rules block (`:161-168` area): Q² thresholds (>0 relevance;
  0.02/0.15/0.35) next to the existing metric-family rule (`:36`, `:162` —
  which already names Q², so this closes the promise rather than adding new
  copy); the persisted `structural_model.q2` block (`:156`) is now fed by
  computed values instead of parsed ones.

### 8.2 M5 / implications (ride-along, no new wiring)

IPMA's `rows` + crosshairs are chart-ready for the M5 implications figure the
roadmap names (`:266-267`); the interpretation sentence is quotable prose. No
M5 code changes in this initiative — the op output is the interface.

## 9. Testing strategy (trust anchor — `libs/thesis-stats/README.md:77-91`)

Every new statistic gets an **independent reference implementation** in the
test, same pattern as `tests/test_pls_accuracy.py:1-10` (reference formulas
recomputed with sklearn/numpy against the engine, TOL 1e-4). Shared fixture:
the seeded 3-construct model, n=300, seed=42 (`tests/conftest.py:13-27,53-70`)
plus a `group` column derived deterministically from it. Do not weaken any
existing tolerance.

### 9.1 Q² (`tests/test_pls_q2.py`)

- **Independent hold-out redundancy loop:** the test re-implements blindfolding
  naively — explicit Python loops over rounds and cells, mean-imputation,
  fresh `PLSEngine` per round, `x̂ = λ·Σβ·score` — and compares Q² per
  endogenous construct to the engine's vectorized result within 1e-9 (same
  algorithm, independent code path) — this pins the implementation. Then the
  **algorithm-level anchors** pin the meaning:
  - noise anchor: replace Z's indicators with pure noise → Q²(Z) ≤ 0;
  - signal anchor: the standard fixture (R²(Y)≈0.3+) → Q²(Y) > 0 and
    Q²(Y) < R²(Y) + 0.05;
  - determinism: two runs → identical dicts; `json.dumps` succeeds.
- Guards: D=6 with n=300, k=3 (900 = 6·150) → `DataError`; D ≥ n → `DataError`;
  D=7 fine. Assert the error message suggests another D.
- q² effect sizes: recomputed by the reference loop with the predictor dropped;
  sign/band sanity.

### 9.2 MICOM + MGA (`tests/test_pls_mga.py`)

- **Seeded reference:** with `seed=42, n_permutations=200`, the test
  re-implements the permutation loop independently (own
  `default_rng(42).permutation` consumption **must** match — the design fixes
  the rng call order: one `rng.permutation(n)` per draw, nothing else consumed
  from the rng inside the loop, making the reference reproducible) and matches
  `c`, `p_c`, `Δ`, `p_permutation` exactly.
- **Null calibration:** split the fixture by a random label independent of the
  data → all compositional `c > 0.99`, all path-diff p > 0.05,
  `invariance_level` ∈ {full, partial}.
- **Planted difference:** simulate group B with β(X→Y) shifted by 0.4 (reuse
  the conftest generator with a different coefficient) → `p_permutation < 0.05`
  for X→Y, other paths clean.
- **Gating:** feed group B whose Y-indicators are re-keyed/garbled so
  compositional invariance fails → `defensible: false` on Y-paths,
  `comparison_defensible: false`, message present, per-group betas still
  returned.
- Guards: 1-level group, 3-level group without `group_values`, group n=15,
  moderation model → typed errors; group n=25 → soft finding.
- Determinism: same seed → identical payload; different seed → p values move.

### 9.3 IPMA (`tests/test_pls_ipma.py`)

- **Hand-computed rescaling:** a tiny 2-construct fixture with known weights
  (e.g. equal weights, Likert 1–5, constant columns where useful) where
  performance is computable by hand (e.g. all-3s column → performance 50.0
  exactly); assert to 1e-9.
- Reference importance: independent OLS (sklearn `LinearRegression`, the
  `test_pls_accuracy.py` style) on the test's own rescaled composites; total
  effects by explicit path enumeration; compare TOL 1e-6.
- Property: every performance ∈ [0, 100]; on standardized-symmetric data
  importance ratios match the engine's standardized total-effect ratios.
- Guards: reversed indicator (negate one column) → hard error naming the
  screening op; unknown/exogenous target → `ModelSpecError`; mixed observed
  scales without explicit bounds → soft `inferred: true` flag present.

### 9.4 Validation layer (`tests/test_validation_bounds.py` + siblings, extend)

- `q2 = 1.2` → hard `bounds.q2`; `q2 = −0.4` → clean; `micom_c = 1.3` → hard;
  `ipma_performance = 130` → hard `bounds.ipma_performance`.
- **Golden-clean:** real `run_pls(..., q2_omission_distance=7)`, `run_mga`,
  `run_ipma` outputs on the clean fixture → adapters emit claims →
  `validate_claims` yields **zero findings** (the `test_validation_golden.py`
  pattern). Mutated payloads (performance=130, c=1.3, diff≠βa−βb) fire the
  named checks.
- Family mix: claims with `q2` + `cfi` → `xtable.family_mix`.

### 9.5 Dothesis-side (`agent/tests/`)

Op wiring tests per the existing pattern (error JSON, validation ride-along
via monkeypatch, summarizer shape) — enumerated in the plan. Golden parity
(`test_golden_parity.py`) must stay green with **zero golden-file changes**
(§3.3).

## 10. Risks

1. **#1 — blindfolding metric mismatch.** Computing SSE in one standardization
   and SSO in another (or predicting standardized while scoring raw) silently
   shifts every Q², and a reference test written from the same misreading
   agrees with the bug. Mitigation is layered: the algorithm fixes the metric
   textually (§4.1 step 3d), the reference loop is written from this spec's
   formula (not from the implementation), and the noise/signal anchors (§9.1)
   fail on any scale error regardless of agreement between the two
   implementations.
2. **Permutation rng drift.** If implementation and reference consume the rng
   differently, the seeded-equality test can never pass and gets "fixed" by
   weakening. The spec pins the consumption contract (§9.2, one
   `rng.permutation(n)` per draw). Do not change it later without recapturing
   the reference.
3. **Small permuted groups.** A permutation draw can hand a group a
   zero-variance indicator → `PLSEngine` still fits (std guarded to 1.0,
   `pls_engine.py:51`) but degenerately. The per-group n ≥ 20 guard plus
   skip-and-count semantics (a failed permutation replicate is dropped and
   counted like `_bootstrap_engine`'s replicate policy, `smartpls.py:387-393`;
   >5% drops → soft finding in the payload) bound this.
4. **IPMA sign/scale abuse.** Negative weights or mixed scales make 0–100
   performance meaningless; both are hard-errored (§4.4), and the [0,100]
   bound is validated after the fact (§7) so even a future bug cannot ship an
   impossible number silently.
5. **fillform coupling.** All engine changes are additive-or-opt-in; golden
   parity enforces it mechanically (§3.3). The submodule commit message must
   flag the new public API for fillform's next `git submodule update --remote`
   (`README.md:67-69`).

## 11. Citations to carry into output payloads / skill copy

- Stone (1974); Geisser (1974) — cross-validation origin.
- Hair, Hult, Ringle & Sarstedt (2017), *A Primer on PLS-SEM*, 2nd ed. — Q²
  procedure, D guidance, 0.02/0.15/0.35 bands.
- Henseler, Ringle & Sarstedt (2016), *Int. Marketing Review* 33(3) — MICOM.
- Chin & Dibbern (2010) — permutation MGA.
- Hair, Sarstedt, Ringle & Gudergan (2018), *Advanced Issues in PLS-SEM* —
  MGA procedure choice.
- Ringle & Sarstedt (2016), *IMDS* 116(9) — IPMA.
