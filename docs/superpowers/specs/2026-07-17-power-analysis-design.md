# Power Analysis Ops — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-power-analysis-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #2 in `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:90-111` (Phase 1, "Power-analysis ops")
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md` §3.1 (early n reality check, :100-104), §3.3 (computed sample plan, :114-127), §3.5(2) (in-line G*Power ritual, :154-156), §3.6 (limitations seeded from post-hoc power, :168-172), checklist item (:273-274)
**Builds on:** `2026-07-17-thesis-stats-shared-lib-design.md` (shipped), `2026-07-17-stats-self-validation-design.md` (shipped — findings/claims machinery this spec extends)

---

## 1. Motivation

Every committee asks **"why n = 214?"** — the G*Power ritual. Today DoThesis
cannot answer it with a computation:

- `agent/sampling.py:13-27` (`target_sample_n`) is explicit that it is
  "Guidance rules, NOT a power-analysis engine — there's no effect-size /
  alpha / power triplet here". It returns 10×-rule / cases-per-predictor
  heuristics only.
- The M3 `sampling_plan` tool (`agent/tools/instrument.py:141-211`) persists a
  `sample_plan` built from those heuristics; the methods pre-flight
  (`agent/preflight.py:32-33`) only checks that `sample_plan.target_n`
  *exists*.
- `rigor.py` has the effect sizes (Cohen's f² at
  `libs/thesis-stats/src/thesis_stats/rigor.py:105-120`, Cohen's d at
  `:123-136`) but no power (grep-verified; also stated in the vision gap list
  `...-vision.md:70-71` and the thesis-stats README "Roadmap (deferred)").
- The mock committee even *asks* the power question
  (`agent/tools/defense.py:29-36`, the small-n heuristic) and its
  `model_answer_hint` can only tell the student to "cite the 10x /
  inverse-sqrt rule" — it cannot compute the answer.

This initiative adds **deterministic power analysis** (no LLM anywhere) as a
new pure module in `thesis-stats` plus a whitelisted `run_stats` op, answering
the three questions a committee asks:

1. **A-priori** — effect size + α + desired power + model complexity →
   **required N** (design-time; replaces the crude heuristic as the primary
   justification in the M3 sample plan).
2. **Post-hoc** — achieved N + effect size + α → **achieved power** (for the
   M4/M5 limitations section, with the observed-power caveats stated).
3. **Sensitivity** — N + α + power → **minimum detectable effect size (MDES)**
   (the methodologically preferred alternative to post-hoc power).

Covered methods: **multiple/linear regression** (Cohen's f²), **bivariate
correlation** (r), **independent-samples t-test** (Cohen's d), and **PLS-SEM**
(inverse-square-root method, Kock & Hadaya 2018, with the 10×-rule
cross-check SmartPLS users expect).

## 2. Scope and non-scope

**In scope**

- A pure module `libs/thesis-stats/src/thesis_stats/power.py` with per-method
  functions and a `run_power(...)` dispatcher (§4, §5).
- A whitelisted `run_stats` op `power` in `agent/tools/stats.py` (§6).
- Self-validation coverage for power outputs — new `power` metric bounds and
  a `claims_from_power` adapter riding the shipped validation layer (§7).
- M3 integration: `sampling_plan` upgraded from heuristic-only to
  power-primary (§8.1); preflight item upgraded (§8.2); rubric rides along
  automatically (§8.3).
- Skill updates: M3 sample-size guidance, M4 op list + limitations guidance
  (§8.5).

**Out of scope (explicitly deferred)**

- ANOVA (>2 groups), chi-square, logistic regression, mediation-specific
  (Monte-Carlo) power, CB-SEM power (MacCallum RMSEA method — belongs with
  roadmap initiative #9, semopy).
- Simulation-based power for PLS-SEM (Kock & Hadaya's Monte-Carlo method) —
  the inverse square root method is their recommended analytical choice and
  what committees in this market recognize.
- The M1 early feasibility check (vision §3.1) — it will call the same
  `run_power` once it lands; no M1 changes here.
- The headless orchestrator M3 agent (`orchestrator/intake.py:77`,
  `orchestrator/schemas/m3.py:27-28` `target_sample_size`) — it collects
  `target_sample_size` via prompt today; wiring `run_power` into the headless
  path is deferred until the headless/interactive convergence work
  (`2026-07-15-headless-deep-agent-convergence-design.md`) settles which
  surface owns it. The schema field is unchanged either way.
- Any LLM involvement. Every number here is closed-form or `statsmodels`.

## 3. Placement decision

| Option | Verdict |
|---|---|
| (a) Compute in `agent/tools/stats.py` only (dothesis-side) | Rejected — fillform (the other thesis-stats consumer) needs the same answer; the functions must be unit-tested against statsmodels next to the engine; and `agent/sampling.py` would remain a second, disagreeing source of sample-size truth. |
| (b) Fold into `run_rigor` as a new check | Rejected — every `rigor` check runs **on a data file** (`run_rigor(data, ...)`, `rigor.py:173`), but a-priori power is **data-free design-time math**; forcing a file argument would be a lie, and M3 (no data yet) is the primary consumer. Post-hoc power does relate to data, but it takes `n` + an already-computed effect size, not raw rows. |
| **(c) New pure `power.py` in `thesis-stats` + a dedicated `run_stats` op `power`** | **Chosen.** Mirrors the shipped layering exactly: pure functions in the submodule (tested against statsmodels + published worked examples), a thin whitelisted op in `agent/tools/stats.py` (lazy import, bounded summary, fail-open validation), and product wiring (sampling_plan / preflight / skills) that consumes the pure functions directly where no file is involved. |

Concretely:

- **`libs/thesis-stats/src/thesis_stats/power.py`** (new) owns all math:
  `power_regression`, `power_correlation`, `power_ttest`, `power_pls_sem`,
  the named-effect-size conventions, the justification-sentence builder, and
  the `run_power(analysis, mode, **params) -> dict` dispatcher. Exported from
  `thesis_stats/__init__.py` (alongside `run_pls`/`run_rigor`,
  `__init__.py:38-53`); `__version__` bumps to `0.3.0`.
  `statsmodels==0.14.5` is already a pinned dependency
  (`libs/thesis-stats/pyproject.toml:23`) — **no new dependency**.
- **`agent/tools/stats.py`** gains `_op_power` + a `"power"` entry in the
  `OPS` whitelist (`stats.py:260-274`), following the lazy-import /
  bounded-payload pattern of the thesis-stats-backed ops (`stats.py:119-127`,
  `:194-200`).
- **`agent/tools/instrument.py`** `sampling_plan` calls
  `thesis_stats.power.run_power` **directly** (pure import, not through
  `run_stats`) because it has no data file, must persist to the store, and is
  already the M3 write path for `sample_plan` (`instrument.py:193-208`).
- **`agent/sampling.py`** `target_sample_n` stays — demoted to the
  **cross-check/floor** role its docstring already describes; it is no longer
  the primary justification.

## 4. Methods and formulas (per analysis)

All modes for all four analyses. α default **0.05**, power default **0.80**
throughout — the two conventions every committee in this market expects.

### 4.1 Regression (multiple/linear) — Cohen's f²

Backed by `statsmodels.stats.power.FTestPowerF2` (present in the pinned
0.14.5), which takes **f² directly** with conventional df naming and
`nobs = df_denom + df_num + 1`:

- **A-priori:** solve `df_denom` from
  `FTestPowerF2().solve_power(effect_size=f2, df_num=k, alpha=α, power=P)`;
  `required_n = ceil(df_denom) + k + 1`.
- **Post-hoc:** `FTestPowerF2().power(effect_size=f2, df_num=k, df_denom=n-k-1, alpha=α)`.
- **Sensitivity:** solve `effect_size` with `df_num=k, df_denom=n-k-1` →
  MDES as f² (banded small/medium/large at .02/.15/.35, matching
  `rigor.py:107` and `_band` at `rigor.py:33-43`).

> **⚠ Implementer note — verified 2026-07-17 against the repo's own venv
> (statsmodels 0.14.5):** use `FTestPowerF2`, **not** `FTestPower`.
> `FTestPower`'s `df_num`/`df_denom` are historically **swapped** relative to
> conventional naming — `FTestPower().power(effect_size=√.15, df_num=3,
> df_denom=73, α=.05)` returns **0.061** (wrong), while swapping the dfs
> returns 0.8018. `FTestPowerF2` with conventional naming reproduces the
> G*Power textbook value exactly: f²=.15, k=3, α=.05, power=.80 →
> `df_denom=72.706` → **N=77**. `FTestPower` also takes Cohen's *f* (√f²),
> another silent-corruption trap. This is the #1 correctness risk of the
> whole initiative; the known-value tests in §9 exist to make it impossible
> to get wrong silently.

Named effect sizes (f²): small=.02, medium=.15, large=.35 (Cohen 1988).
Floor: `required_n ≥ k + 2` (else the F test has no df).

### 4.2 Correlation (bivariate r) — Fisher-z approximation

Closed-form (scipy.stats.norm only), the standard Cohen (1988) approach:

- `C = arctanh(|r|)`;
- **A-priori:** `n = ceil( ((z_{1-α/2} + z_P) / C)² + 3 )`;
- **Post-hoc:** `power = Φ( √(n-3)·C − z_{1-α/2} )`;
- **Sensitivity:** `C = (z_{1-α/2} + z_P)/√(n-3)`, `MDES r = tanh(C)`.

Named effect sizes (r): small=.10, medium=.30, large=.50.
Documented divergence: the Fisher-z approximation gives N=85 for r=.30
(α=.05, power=.80) where G*Power's exact routine gives 84 — a ±1 divergence
the output's `assumptions` list discloses ("Fisher-z approximation"). One- or
two-sided via `alternative` (default two-sided).

### 4.3 Independent t-test — Cohen's d

Backed by `statsmodels.stats.power.TTestIndPower` (noncentral-t, exact):

- **A-priori:** `solve_power(effect_size=|d|, alpha=α, power=P, ratio=ratio,
  alternative=alt)` → per-group `n1 = ceil(·)`; report
  `required_n = n1 + ceil(n1·ratio)` (total) plus `per_group`.
- **Post-hoc:** `power(effect_size=|d|, nobs1=n1, ratio=n2/n1, ...)` — the op
  accepts either total `n` (split by `ratio`, default 1.0) or explicit
  `n1`/`n2`.
- **Sensitivity:** solve `effect_size` → MDES d (banded .2/.5/.8, matching
  `cohens_d` at `rigor.py:123-136`).

Named effect sizes (d): small=.20, medium=.50, large=.80. Verified: d=.50,
α=.05, power=.80, two-sided → 63.77 → **64 per group, N=128** (textbook).

### 4.4 PLS-SEM — inverse square root method (Kock & Hadaya 2018)

The method SmartPLS users and this market's committees expect, plus the
10×-rule cross-check:

- **A-priori (primary):** `required_n = ceil( ((z_{1-α} + z_P) / |β_min|)² )`
  where `β_min` is the minimum absolute standardized path coefficient
  expected to be significant. Kock & Hadaya's constant 2.486 for α=.05 /
  power=.80 is exactly `z_.95 + z_.80` — the method is **one-tailed** (path
  hypotheses are directional); compute the z-sum from α and power rather than
  hard-coding 2.486 so other α/power combinations work. Verified against the
  paper's worked examples: β_min=.197 → (2.486/.197)² = 159.2 → **160**;
  β_min=.146 → 289.9 → **290**.
- **Cross-check (always reported alongside):** the 10-times rule —
  `10 × max arrows pointing at any construct` (Hair et al. 2017) — returned
  in `cross_checks`, never as the primary number (Kock & Hadaya's paper
  exists precisely because the 10× rule under-powers small-β models).
  The recommended `target_n` is `max(inverse_sqrt_n, ten_times_n)`.
- **Post-hoc:** `power = Φ( |β_min|·√n − z_{1-α} )` (the same normal
  approximation inverted).
- **Sensitivity:** `MDES β_min = (z_{1-α} + z_P)/√n`.

`effect_size` for pls-sem is **β_min**, not f². Named sizes map to
β_min = .10/.20/.30 (weak/moderate/strong path) with an explicit
`assumptions` entry saying the student should replace the convention with the
smallest path they hypothesize (from a pilot or the literature).

### 4.5 Post-hoc power: the mandatory caveat

Post-hoc mode always returns a `caveats` entry: *observed power computed from
the observed effect size is a one-to-one function of the p-value and adds no
evidential information (Hoenig & Heisey 2001); report it only as a
limitations-section disclosure, and prefer sensitivity (MDES) when arguing
what the study could/could not detect.* The M4 skill guidance (§8.5) repeats
this so the agent never sells post-hoc power as proof of adequacy.

## 5. Pure API (`thesis_stats/power.py`)

```python
run_power(
    analysis: str,          # "regression" | "correlation" | "ttest" | "pls_sem"
    mode: str = "apriori",  # "apriori" | "posthoc" | "sensitivity"
    effect_size: float | str | None = None,  # number, or "small"/"medium"/"large"
    alpha: float = 0.05,
    power: float = 0.80,    # ignored in posthoc mode
    predictors: int | None = None,  # regression: k; pls_sem: max arrows into any construct
    n: int | None = None,   # required for posthoc/sensitivity
    n1: int | None = None, n2: int | None = None,  # ttest posthoc alternative to n
    ratio: float = 1.0,     # ttest group-size ratio
    alternative: str = "two-sided",  # ttest/correlation
) -> dict
```

Behavior rules:

- **Pure and deterministic** — same inputs, same output; no I/O, no RNG.
- Named `effect_size` (or `None` → `"medium"` default) resolves through the
  per-analysis convention table (§4); the resolution is recorded in
  `inputs.effect_size_label` so "assumed medium" is never silent.
- Validation raises `ValueError` with a plain message on: effect_size ≤ 0
  (after `abs()` for d), α ∉ (0, 1), power ∉ (0, 1) or power ≤ α, missing
  `predictors` for regression/pls_sem, missing `n` for posthoc/sensitivity,
  `n ≤ predictors + 1` for regression post-hoc, non-2 group specs. The op
  layer converts these to the standard `{"error": ...}` JSON
  (`stats.py:369-375` already does this for any raising op).
- A statsmodels solver non-convergence (returns nan + `ConvergenceWarning`)
  is caught and re-raised as `ValueError("power solver did not converge for
  these inputs")` — never let nan escape into a payload.
- `required_n` is always rounded **up** (`ceil` with a 1e-9 guard);
  `achieved_power` rounded to 4 dp; MDES to 4 dp.
- `required_n > 100_000` still returns but appends a caveat ("effect size
  implausibly small for a survey design").

## 6. The `run_stats` op contract

`run_stats(op="power", file=?, params={...})` — params mirror §5 exactly
(`analysis`, `mode`, `effect_size`, `alpha`, `power`, `predictors`, `n`,
`n1`, `n2`, `ratio`, `alternative`).

- **`file` is optional-in-practice:** the op ignores it for a-priori mode
  (the model may pass `""`). For posthoc/sensitivity, when `n` is omitted
  **and** a real file is given, `n` defaults to the file's row count via
  `_load_df` (`stats.py:21-32`) — the one data-touching convenience, and the
  reason the op lives in `run_stats` rather than a separate tool.
- Lazy import (`import thesis_stats` inside `_op_power`) so a missing install
  degrades to the existing "stats dependency missing" JSON error
  (`stats.py:371-372`).
- The result is the `run_power` dict verbatim — already bounded (a dozen
  scalar fields, no matrices), already JSON-serializable, rounded via the
  existing `_round_floats` (`stats.py:130-137`).

### Output shape (committee-ready, bounded)

Only the active mode's result key is present; nulls are dropped.

```json
{
  "op": "power",
  "analysis": "regression",
  "mode": "apriori",
  "inputs": {"effect_size": 0.15, "effect_size_label": "medium (Cohen's f²)",
             "effect_metric": "f2", "alpha": 0.05, "power": 0.8, "predictors": 3},
  "required_n": 77,
  "assumptions": ["F test of R² deviation from zero, fixed model",
                  "medium effect assumed (no pilot estimate supplied)"],
  "justification": "An a priori power analysis for multiple regression with 3 predictors, assuming a medium effect size (f² = .15), α = .05 and desired power = .80, indicates a minimum required sample of N = 77 (Cohen, 1988; Faul et al., 2009).",
  "citations": ["Cohen (1988)", "Faul, Erdfelder, Buchner & Lang (2009)"],
  "method": "statsmodels.stats.power.FTestPowerF2"
}
```

Mode/analysis variants: `"achieved_power": 0.998` (posthoc, plus the Hoenig &
Heisey caveat in `caveats`); `"mdes": {"metric": "f2", "value": 0.0747,
"interpretation": "small-to-medium"}` (sensitivity); for `pls_sem`,
`"cross_checks": [{"rule": "10-times rule", "required_n": 30, "citation":
"Hair, Hult, Ringle & Sarstedt (2017)"}]` and the justification names the
inverse square root method (Kock & Hadaya, 2018).

The `justification` sentence is the **product surface**: M3's sample-size
rationale quotes it verbatim (§8.1), M5's Chapter 3 renders it, and the
defense drill's model-answer hint cites it (§8.4). It is built by a
deterministic template per (analysis, mode) — no LLM.

## 7. Self-validation integration

The shipped validation layer (`libs/thesis-stats/src/thesis_stats/validation.py`)
treats a bad power number like any other bad statistic:

1. **Metric registry** (`validation.py:24-29`): add `"power"` and `"d"`.
2. **Bounds checks** (`validation.py:109-201` `_bounds`):
   - `power` ∈ [0, 1] → outside is **hard** (`bounds.power`);
   - `n` already has `> 0` **hard** (`validation.py:195-197`); extend with an
     integer-ness rule for claims flagged `{"integer": true}` — a fractional
     required N is **hard** (`bounds.n_integer`);
   - `f2 ≥ 0` already exists (`validation.py:168-171`); `d` gets a **soft**
     plausibility bound (|d| > 5 is a data-entry error in practice);
     correlation MDES reuses the existing `corr` |r| ≤ 1 hard bound.
3. **Adapter** — `claims_from_power(result)` in `validation.py` (engine-native,
   next to `claims_from_rigor`): emits `power` (achieved), `n`
   (required_n, flagged integer), and the effect-size claim
   (`f2` / `corr` / `d` / `beta` for β_min). Registered in `validate_result`
   dispatch (`validation.py:815-830`) under kind `"power"`.
4. **Dothesis side** — `claims_from_run_stats` (`agent/stats_validation.py:57`)
   gains an `op == "power"` branch delegating to `claims_from_power`. The
   existing fail-open attach in `run_stats` (`stats.py:376-386`) then covers
   the new op with **zero further wiring**, and the M4 commit gate
   (`agent/tools/state_tools.py:117` `stats_validation_failed`) blocks a
   hard-bad power number exactly like a hard-bad loading.

Rationale for bounds-only coverage: `power.py` itself deterministically
enforces input consistency (§5), so the validation layer's job here is what
it is everywhere else — catching **mutated, mis-parsed, or hand-typed**
payloads (e.g. a student pastes "achieved power = 1.4" from a bogus source),
not re-deriving the math.

## 8. Product integration (advisory, never blocking)

### 8.1 M3 `sampling_plan` — the primary consumer

`agent/tools/instrument.py:156-209` upgrades from heuristic-only to
**power-primary with heuristic floor**:

1. Derive `analysis` from `methodology` (same keyword mapping as
   `target_sample_n`, `agent/sampling.py:21-27`: "pls" → `pls_sem`,
   "cb-sem"/"amos" → keep heuristic-only for now (CB-SEM power is deferred,
   §2), default → `regression`).
2. Derive `predictors`: for regression, the count of arrows into the
   dependent construct; for PLS-SEM, the **max in-degree over all
   constructs** — note this *fixes* the current approximation, which counts
   *total* edges (`instrument.py:173`) rather than Hair's "largest number of
   arrows pointing at any construct" (`sampling.py:24-25`).
3. Call `run_power(analysis, mode="apriori", effect_size="medium", ...)`
   (pure import; students rarely have a pilot estimate at M3 — the
   `effect_size_label` records the assumption and the agent may override with
   a user-supplied value).
4. Persist (same `commit_slice("M3", {"sample_plan": ...})` write path,
   `instrument.py:203-208`):

```json
{
  "target_n": 160,
  "power_analysis": { ...the run_power result verbatim... },
  "method_rule": "PLS-SEM: 10x the largest number of arrows into a construct (Hair et al.).",
  "rationale": "<power justification sentence> The 10-times rule cross-check gives N = 60; the larger value is adopted. Plan ~10-15% over target for invalid/careless responses.",
  "screening": "...", "timeline_weeks": 3
}
```

   `target_n = max(power_n, heuristic_n)` — never below either convention, so
   the plan survives both a G*Power-literate committee and a
   rules-of-thumb-literate one. **Fail-open:** if `run_power` raises or
   thesis_stats is missing, fall back to today's heuristic-only plan
   (log, per the tool's existing best-effort posture, `instrument.py:203-208`).
   Backward compatible: `target_n` keeps its name/meaning, so the preflight
   (`preflight.py:32`), the defense heuristic (`defense.py:30`), and the
   Field-It surface read on unchanged.

### 8.2 Methods preflight — design-readiness surface

`agent/preflight.py:18-42` (`preflight_check`) upgrades the sample item from
existence-checking to power-awareness, still returning advisory strings:

- No `sample_plan.target_n` → existing message, now pointing at the fix:
  `"Sample size not planned — run sampling_plan (computes an a-priori power-based N)."`
- `target_n` present but no `sample_plan.power_analysis` → **new** item:
  `"Sample size planned but not power-justified — re-run sampling_plan so 'why n=X?' has a computed answer."`

Advisory, never a gate — the module docstring's Global Constraint
(`preflight.py:1-6`) is unchanged.

### 8.3 Rubric — rides along for free

`quality/rubric.py:111-127` (`preflight_dimension`, weight 0.10) reuses the
SAME `preflight_check` pure function, so the new advisory item lowers the
design-readiness score for un-power-justified plans with **zero rubric code
changes**. One rubric test asserts the ride-along (plan §Phase 5).

### 8.4 Mock committee — a computed model answer

`agent/tools/defense.py:29-36`: when `sample_plan.power_analysis` exists, the
small-n question's `model_answer_hint` quotes the computed `justification`
sentence (and, when n < required_n, flags the shortfall as the honest
limitation) instead of the generic "cite the 10x / inverse-sqrt rule". Pure
change inside `_state_weakpoints`; heuristic fallback unchanged.

### 8.5 Skills

- **M3** (`skills/dothesis-m3-design/SKILL.md:109-110` "State sample-size
  logic", `:84-85` moderator cost, `:149` quality bar): the sample-size logic
  step now instructs calling `sampling_plan` (which computes the a-priori N)
  and quoting its justification sentence; the moderator-cost example
  ("~120 → ~180") can cite that the number comes from a real computation.
- **M4** (`skills/dothesis-m4-analysis/SKILL.md:42-66` op list): add the
  `power` op with its params, a one-line description per mode, and the
  post-hoc caveat rule (§4.5); the pipeline's interpretation guidance gains
  "seed the limitations note with post-hoc/sensitivity results when
  achieved n < planned n". The op-list docstring in `run_stats`
  (`stats.py:335-361`) gets the matching entry.

## 9. Testing strategy

All known values below were **verified against the repo's installed
statsmodels 0.14.5** on 2026-07-17.

### 9.1 Known-value tests (`libs/thesis-stats/tests/test_power.py`)

| Case | Inputs | Expected |
|---|---|---|
| Regression a-priori (the textbook case) | f²=.15, k=3, α=.05, power=.80 | **N = 77** (G*Power) |
| Regression post-hoc | f²=.15, k=3, N=200 | power ≈ **0.998** (assert > 0.99) |
| Regression sensitivity | k=3, N=150, α=.05, power=.80 | MDES f² ≈ **0.0747** (±.001) |
| t-test a-priori | d=.5, α=.05, power=.80, two-sided | **64/group, N=128** |
| Correlation a-priori | r=.30, α=.05, power=.80 | **N = 85** (Fisher-z; document G*Power exact = 84) |
| PLS inverse-sqrt (Kock & Hadaya worked ex.) | β_min=.197, α=.05, power=.80 | **N = 160** |
| PLS inverse-sqrt (second worked ex.) | β_min=.146 | **N = 290** |
| PLS cross-check | max in-degree 4 | ten-times rule entry = 40; `target` recommendation = max |
| Named sizes | `effect_size="medium"` per analysis | resolves to .15 / .30 / .50 / .20 with label recorded |

### 9.2 Edge/contract tests

effect_size 0 or negative-after-abs → ValueError; α=0/1, power≤α →
ValueError; posthoc without n (and no file) → ValueError; regression n ≤ k+1
→ ValueError; d passed negative → |d| used, noted in assumptions; f²=1e-9 →
returns with the implausibly-small caveat; solver nan → clean ValueError;
determinism (two calls, identical dicts); every payload
`json.dumps`-serializable; the `FTestPowerF2`-not-`FTestPower` regression
test (assert the a-priori N for the textbook case is 77, which fails loudly
if anyone "simplifies" back to `FTestPower`).

### 9.3 Validation-layer tests

`power` claim 1.2 → hard `bounds.power`; required_n 76.5 with integer flag →
hard `bounds.n_integer`; d = 7 → soft; clean `run_power` outputs for all
4×3 analysis/mode combos → **zero findings** (golden-clean, mirrors
`test_validation_golden.py`'s pattern).

### 9.4 Dothesis-side tests

`_op_power` through `run_stats` (op JSON contract, error JSON on bad params,
file-derived n for posthoc); `sampling_plan` persistence shape + fail-open
fallback (`agent/tests/` — extend `test_stats_tool.py`, add
`test_sampling_plan` cases wherever `make_sampling_plan_tool` is currently
covered); preflight new-item cases (`test_m3_contract.py` or the preflight
tests); rubric ride-along; defense hint upgrade.

## 10. Risks

1. **The statsmodels `FTestPower` df-swap trap** (§4.1) — mitigated by
   mandating `FTestPowerF2` + the known-value tests that fail loudly on the
   wrong class or on passing f instead of f².
2. **Effect-size defaults oversold** — an assumed-medium a-priori N presented
   as gospel is its own committee risk. Mitigated by always recording
   `effect_size_label`, surfacing the assumption in `assumptions`, and skill
   guidance to ask for a pilot/literature estimate.
3. **Observed-power misuse** — mitigated by the always-on caveat (§4.5) and
   M4 skill language; sensitivity mode exists precisely as the defensible
   alternative.
4. **`target_n` semantic drift** — consumers read `sample_plan.target_n`
   today (preflight, defense, Field-It); mitigated by keeping the key and
   only *adding* `power_analysis` (§8.1), with a test asserting the old keys
   survive.
