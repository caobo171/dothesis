# CB-SEM Compute (`run_stats` op `cb_sem`) — Design Spec

**Date:** 2026-07-17
**Status:** Ready for implementation planning
**Roadmap:** initiative #9, `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:278-297`
**Vision:** `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-vision.md:79-82, 155-160`
**Companion plan:** `docs/superpowers/specs/2026-07-17-cb-sem-plan.md`

---

## 1. Motivation

Half the method market is parse-only. Today a CB-SEM student can only *paste*
lavaan/AMOS output — `orchestrator/tools/m4_parsers/lavaan.py:7-47` regex-extracts
CFI/TLI/RMSEA/SRMR from pasted text; nothing computes them. Meanwhile:

- The **method advisor (#7, shipped)** actively recommends CB-SEM under
  normality + n ≥ 150 conditions (`agent/method_advisor.py:112-120` sample
  floor, `:94` "latent model favors cb_sem") — so the product steers students
  toward a method it then cannot execute.
- The **self-validation layer (#1, shipped)** already knows the CB-SEM metric
  family: `cfi`/`tli`/`rmsea`/`srmr`/`chi2_df` are registered metrics
  (`libs/thesis-stats/src/thesis_stats/validation.py:27-28`), bounds checks
  exist for all of them (`validation.py:179-191`), `loading_cbsem` has a
  Heywood-aware soft bound (`validation.py:147-150`), and the PLS/CB-SEM
  family-mix check is live (`validation.py:488-489, 514-521`). The persisted
  `analysis_results.structural_model.{cfi,tli,rmsea,srmr}` keys are already
  read at the M4 commit gate (`agent/stats_validation.py:294-297`).
- The **M4 skill** already enforces family consistency for *parsed* CB-SEM
  results (`skills/dothesis-m4-analysis/SKILL.md:36-38`: "CB-SEM →
  CFI/TLI/RMSEA/SRMR + loadings. Never report both.").

This initiative closes the loop: a new whitelisted `run_stats` op `cb_sem`
computes the CFA measurement model + structural model from the student's raw
uploaded data, in the same bounded-JSON shape family as the PLS ops, gated by
the same self-validation machinery.

## 2. Scope and non-scope

**In scope (v1):**

1. **CFA / measurement model:** standardized loadings, per-construct
   Cronbach's α, CR, AVE; fit indices χ² (+p), χ²/df, CFI, TLI, RMSEA with
   90% CI, SRMR.
2. **Structural model:** path coefficients (unstandardized + standardized)
   with SE/z/p, R² per endogenous construct; the same fit indices for the
   full SEM.
3. Optional `residual_covariances` (item-pair error correlations) — needed
   both by real committee practice and to reproduce the published Political
   Democracy reference values (§9.1).
4. Estimator: **ML only** (semopy objective `MLW`, the Wishart ML that
   matches lavaan's default `ML` on complete data). `estimator` param exists
   with default `"ML"`; anything else is a clean typed error naming the
   supported set.
5. Missing data: **listwise deletion** over the scoped (measurement) columns,
   with the dropped-n disclosed in the payload.
6. Heywood / non-convergence: clean typed error or soft finding — never a
   crash, never a garbage fit (§6.4).

**Out of scope (v1), each with the reason:**

- **Modification indices.** The roadmap's "modification-index highlights"
  (`roadmap.md:286-288`) cannot come from semopy: `grep -rl modification
  semopy/` over the 2.3.11 sdist finds **nothing** — semopy has no MI
  implementation, and hand-rolling lavaan-style univariate score tests is a
  research project of its own. v1 ships the cheap defensible substitute:
  the top-|residual| standardized covariance residuals (§5.4), computed from
  the same matrices as SRMR, as respecification *hints*.
- **FIML / robust estimators (MLM/MLR) / WLSMV-categorical.** semopy offers
  `FIML`/`ULS`/`GLS` objectives but none were validated against lavaan here;
  each needs its own reference anchor before it can ship (trust-anchor rule,
  `libs/thesis-stats/README.md:77-92`).
- **Latent moderation / interaction terms.** CB-SEM latent interactions need
  product-indicator or LMS machinery. A `moderate_effect` node in the model
  → clean `ModelSpecError` telling the student to use the PLS `moderation`
  op or model the interaction explicitly.
- **Second-order constructs, measurement invariance (CB-SEM MGA), mean
  structures.** Later initiatives.

## 3. Placement

The estimator lives in the **submodule**: new module
`libs/thesis-stats/src/thesis_stats/cbsem.py`, public entry `run_cbsem`,
exported from `libs/thesis-stats/src/thesis_stats/__init__.py` (version
`0.6.0` → `0.7.0` at `__init__.py:38`) — exactly the placement the roadmap
names (`roadmap.md:292-294`) and the pattern every prior engine extension
followed (power, screening, MGA/IPMA). Validation additions also live in the
submodule (`validation.py`); the dothesis side only gets the op wrapper, the
claims branch, and skill copy.

## 4. The semopy dependency decision (the #1 risk)

### 4.1 Facts established empirically (2026-07-17, clean venv, exact pins)

All of the following was verified in a scratch venv built from the exact
pinned set in `libs/thesis-stats/pyproject.toml:19-27` (pandas 2.3.2, numpy
2.3.3, scipy 1.16.2, statsmodels 0.14.5, scikit-learn 1.7.2,
factor-analyzer 0.5.1, pydantic 2.11.9) plus `semopy==2.3.11`:

1. **semopy is NOT currently importable** in the dothesis env
   (`api/.venv/bin/python -c "import semopy"` →
   `ModuleNotFoundError`). It must be added.
2. **`pip install semopy==2.3.11` does not move a single pin.** semopy's
   `setup.py` declares only unpinned floors
   (`install_requires=['scipy','numpy','pandas','sympy','scikit-learn',
   'statsmodels','numdifftools']`), all satisfied by the pinned stack. The
   resolve adds exactly two new packages: **`sympy==1.14.0`** and
   **`numdifftools==0.9.42`** (both pure-Python). The EFA-breaking scenario
   the README warns about (`libs/thesis-stats/README.md:71-75`) cannot
   recur through this install: nothing already-pinned is re-resolved.
3. **semopy 2.3.11 works under numpy 2.x on our exact stack.** Fitting the
   Holzinger–Swineford CFA and the Political Democracy SEM reproduced
   lavaan's published values (full table in §9.1): HS39 χ² = 85.30573,
   df = 24, CFI = 0.93056, TLI = 0.89584, RMSEA = 0.09228, standardized
   loadings matching lavaan `std.all` to 3 dp; PD χ² = 38.125, df = 35,
   CFI = 0.9954, TLI = 0.9927, RMSEA = 0.0347.
4. **Known numpy-2 landmines inside semopy — on paths we never call:**
   `semopy/model_generalized_effects.py:548` uses `np.float(...)` and
   `semopy/regularization.py:71` uses `np.int` — both removed in numpy ≥ 1.24
   and fatal if executed. They sit inside function bodies, so `import semopy`
   succeeds; our path (`Model`, `Model.fit`, `Model.inspect`, `calc_stats`)
   never reaches them. **Rule for the implementation: never call
   `ModelGeneralizedEffects`, `ModelEffects`, or `create_regularization` —
   they are broken under our numpy.** The wrapper must not expose them.
5. `semopy.plot` guards its `graphviz` import in try/except
   (`plot.py:7-14`) — no hidden hard dependency.
6. **semopy provides no SRMR and no RMSEA CI** — `calc_stats` returns
   DoF, χ² (+baseline), CFI, GFI, AGFI, NFI, TLI, RMSEA, AIC, BIC, LogLik
   only (verified against the fitted HS39 model, and by inspection of
   `semopy/stats.py`). SRMR and the RMSEA CI are hand-computed (§5.2, §5.3),
   each with its own independent lavaan reference (§9.1).

### 4.2 Decision

**Pin `semopy==2.3.11` (+ its two new transitive deps) as an *optional
extra* of thesis-stats, not a core dependency:**

```toml
# libs/thesis-stats/pyproject.toml
[project.optional-dependencies]
dev = ["pytest>=7.0"]
cbsem = ["semopy==2.3.11", "sympy==1.14.0", "numdifftools==0.9.42"]
```

Rationale:

- **fillform's validated env stays byte-identical.** The submodule is shared
  (`README.md:50-57`); fillform has no CB-SEM feature and should not inherit
  sympy/numdifftools churn. An extra keeps the blast radius at zero.
- **The pins philosophy extends to the transitives.** semopy's own floors are
  unpinned, so `sympy`/`numdifftools` would silently float on every fresh
  install; pinning the exact versions validated today (`1.14.0` /
  `0.9.42`) is the same load-bearing-pin discipline as the core set.
- **The fail-soft path becomes first-class** (§4.3) rather than an
  exceptional condition, mirroring the lazy-import degradation already used
  by every thesis-stats-backed op (`agent/tools/stats.py:119-125, 505-506`).

**dothesis wiring:** `dev.sh:155-157` currently installs
`pip install -e libs/thesis-stats` *only when* `import thesis_stats` fails —
so on an existing env the new extra would never install. Both installers
change to the extra form and the dev.sh guard also probes semopy:

- `dev.sh`: guard becomes `python -c "import thesis_stats, semopy"`;
  install becomes `pip install -e "libs/thesis-stats[cbsem]"`.
- `scripts/deploy.sh:197`: `pip install --quiet -e "./libs/thesis-stats[cbsem]"`
  (this line always runs, so deploys pick it up unconditionally).

### 4.3 Fail-soft path (estimator absent)

`cbsem.py` imports semopy **lazily inside `run_cbsem`** (module import of
`thesis_stats.cbsem` must succeed without semopy, same posture as
`agent/tools/model_adapter.py:4-6`). On `ModuleNotFoundError` it raises a new
typed error:

```python
class EstimatorUnavailableError(ThesisStatsError):
    """semopy is not installed — CB-SEM cannot be computed."""
# message: "CB-SEM estimator unavailable — install thesis-stats[cbsem]
#           (semopy==2.3.11), e.g. re-run ./dev.sh"
```

No new plumbing is needed on the dothesis side: `run_stats`'s existing
generic exception handler (`agent/tools/stats.py:507-509`) converts it to
`{"error": "cb_sem failed: CB-SEM estimator unavailable — ..."}` — a clean
JSON error, never a crash. The submodule's CB-SEM tests
`pytest.importorskip("semopy")` so the suite stays green in envs without the
extra (fillform), except the fail-soft test itself, which runs everywhere by
simulating the missing module.

## 5. Computation

### 5.1 AdvanceModel → lavaan-style syntax

`run_cbsem(model, data, estimator="ML", residual_covariances=None)` accepts
the same `AdvanceModel | dict` as every entry point (`__init__.py:81-87`
coercion, `:100-123` measurement check with `strict=True` like `run_pls`).
The dothesis op reuses `agent/tools/model_adapter.py:47-63` unchanged — all
three conceptual-model shapes flow through the existing adapter; **no new
model plumbing on the agent side.**

A pure function `_to_lavaan_desc(model) -> (desc, fwd_map, rev_map)` builds
the semopy description:

- **Sanitization.** lavaan-syntax tokens must be identifier-like, but node
  labels are free text ("Perceived Usefulness") and item columns can contain
  spaces/dots. Map every construct label and item column through
  `re.sub(r"\W+", "_", name)` (prefix `v_` if it starts with a digit;
  de-duplicate with numeric suffixes). The DataFrame columns are renamed with
  the same map before fitting; **all output keys use the original names** via
  the reverse map.
- **Measurement lines.** One per variable node:
  `San(label) =~ San(q1) + San(q2) + ...` from `node.questions` (already
  overridden by `params.measurement` in the adapter,
  `model_adapter.py:41-44`).
- **Structural lines.** Group edges by target:
  `San(target) ~ San(src1) + San(src2)`. `effectType`
  (`models.py:51-58`) is hypothesis direction only — it does not change the
  syntax; it is echoed per path in the payload so the skill can narrate
  sign-vs-hypothesis.
- **Residual covariances.** `residual_covariances=[["y1","y5"], ...]`
  (original column names) → `San(y1) ~~ San(y5)` lines. Pairs referencing
  unknown columns → `DataError`.
- **Rejections (all `ModelSpecError`, clean messages):** any
  `moderate_effect` node (§2 non-scope); a construct with < 2 indicators
  (single-indicator latents are unidentified in CFA without extra
  constraints; the error tells the student the minimum); self-loop or
  duplicate edges. A construct with exactly 2 indicators is *allowed* but
  produces a payload warning ("2-indicator construct — ≥ 3 recommended;
  identification relies on the full model").
- No edges → pure CFA (measurement + fit, empty `paths`). Edges → full SEM.

### 5.2 What semopy computes natively vs. what we hand-compute

| Quantity | Source | Notes |
|---|---|---|
| Parameter estimates, SE, z, p | `Model.fit` + `Model.inspect(std_est=True)` | `Est. Std` column = standardized solution; z/p are Wald tests. Loadings for marker items (λ fixed = 1) have no SE — reported with `se: null`. |
| χ², df, χ² p, CFI, TLI, RMSEA | `semopy.calc_stats(model)` | Verified against lavaan (§9.1). χ²/df computed by us as the trivial ratio. |
| **SRMR** | **hand-computed** | semopy has none. Formula: with `S = model.mx_cov` (sample cov) and `Σ̂ = model.calc_sigma()[0]` (implied cov), correlation-metric residuals `R_s − R_σ` over the lower triangle **including the diagonal**, `SRMR = sqrt(mean(resid²))`. Verified: HS39 → 0.0652 (lavaan 0.065), PD → 0.0445 (lavaan 0.044). Independent reference pinned in the anchor test (§9.1). |
| **RMSEA 90% CI** | **hand-computed** | Invert the noncentral-χ² CDF with `scipy.stats.ncx2` + `brentq`: λ_lo solves `ncx2.cdf(χ², df, λ) = 0.95`, λ_hi solves `= 0.05`, bound = `sqrt(λ/(df·(n−1)))`, clamped at 0. Verified: HS39 → (0.072, 0.114) vs lavaan's (0.071, 0.114) — the 0.001 gap is lavaan's N vs our N−1 denominator convention (kept N−1 to match semopy's RMSEA point estimate); anchor tolerance ±0.003 (§9.1). |
| **R² per endogenous construct** | **hand-computed (one-liner)** | From the standardized solution: for an endogenous latent η, the `η ~~ η` row's `Est. Std` **is** the standardized residual variance ψ_std, so `R² = 1 − ψ_std`. Verified identity on a single-predictor model: R² equals (std β)² exactly. The PD anchor pins this identity for `dem60 ~ ind60`. |
| **Cronbach's α** | **hand-computed from raw items** | Standard `k/(k−1)·(1 − Σvar_i/var_total)` over the construct's scoped columns (same formula as `agent/tools/stats.py:64-73`), independent of semopy. |
| **CR, AVE** | **hand-computed from standardized loadings** | `AVE = mean(λ²)`, `CR = (Σ|λ|)² / ((Σ|λ|)² + Σ(1−λ²))` — the same formulas the self-validation C1/C2 checks recompute (`validation.py:335-357`), which is deliberate: computed output must be exactly self-consistent (golden-clean, §9.4). |
| **Residual highlights** | **hand-computed** | Top 5 |standardized residual| off-diagonal entries of `R_s − R_σ` (the SRMR intermediates), as `[{pair, std_residual}]` — the v1 stand-in for modification indices (§2). |

### 5.3 Estimation mechanics

- `Model(desc)` then `model.fit(df, obj="MLW", solver="SLSQP")`. `MLW` is
  semopy's default and the lavaan-ML equivalent on complete data — the
  reference anchors prove the equivalence.
- Listwise: `df = df[scoped_cols].dropna()`; `n_dropped` disclosed. `n < 2 ×
  n_free_parameters` does not block (advisory product) but adds a warning;
  `n ≤ number of observed variables` → `DataError` (covariance singular by
  construction).
- Determinism: the ML path has no RNG (deterministic starting values, SLSQP);
  same input → identical output dict. Pinned by a test (§9.5). Note
  `Model.fit` reuses previous results as warm starts on successive fits
  (`semopy/model.py:1073-1076`) — the wrapper creates a **fresh `Model` per
  call** so results never depend on call history.

### 5.4 Failure taxonomy (spec item 5 — never a crash, never a garbage fit)

| Condition | Detection | Behavior |
|---|---|---|
| Non-convergence | `SolverResult.success is False` (attrs verified: `success`, `fun`, `message`, `n_it`) | Typed `EstimationError(ThesisStatsError)` → op returns `{"error": "CB-SEM estimation did not converge — <solver message>. Common causes: too few cases, near-collinear items, a mis-specified model."}`. **No numbers are returned.** |
| Numerical blow-up (singular covariance, LinAlgError, NaN objective) | try/except around fit + `calc_stats`; NaN scan on the fit dict | Same `EstimationError`, cause-specific message (e.g. a zero-variance item is named). |
| Heywood case | Empirically, semopy's SLSQP bounds clamp variances at ≥ 0, so Heywood surfaces as a **boundary solution**: residual variance ≤ 1e−6 or a standardized loading ≥ 0.999 (verified on a degenerate n=12 fixture: item variances driven to exactly 0.0). Detect via the `~~` diagonal of `inspect` + the std loadings; also flag any strictly negative variance defensively. | **Soft finding, not an error**: result returned with `warnings: [{"kind": "heywood_case", "where": item/construct, "detail": ...}]`; the self-validation layer independently flags any \|λ\| > 1 as soft `bounds.loading_heywood` (`validation.py:147-150`). The skill copy tells the agent to narrate it as a respecification signal, never as a clean result. |
| Saturated / under-identified (df ≤ 0) | `calc_stats` DoF | Fit-index block replaced by `fit: {"note": "model has df ≤ 0 — fit indices are undefined"}`; estimates still returned; warning added. |
| semopy absent | lazy import | `EstimatorUnavailableError` (§4.3). |

## 6. The op contract and payload

### 6.1 `run_stats(op="cb_sem", file, params)`

Registered in `OPS` (`agent/tools/stats.py:366-385`) following the
thesis-stats-backed pattern (`stats.py:194-207`):

```python
def _op_cb_sem(file, conceptual_model=None, measurement=None,
               estimator="ML", residual_covariances=None, **_):
    import thesis_stats as ts
    model = _adapt(conceptual_model, measurement)      # stats.py:144-148
    raw = ts.run_cbsem(model, _records(file), estimator=estimator,
                       residual_covariances=residual_covariances)
    return _round_floats(raw)                          # stats.py:130-137
```

Params: `conceptual_model` (required, any of the three shapes),
`measurement` (construct → columns, same semantics as `pls_sem`),
`estimator` (default `"ML"`, sole v1 value), `residual_covariances`
(optional item pairs). Advisory posture: the op **never blocks** beyond the
existing self-validation ride-along (`stats.py:510-521`) and the existing M4
commit gate — identical to every other op.

### 6.2 Payload (bounded JSON, PLS shape family)

Same family as `_summarize_pls` (`stats.py:151-191`) so the M4 skill,
persisted block, and validation adapters reuse their mental model —
construct-level tables only, never row-level data, floats 4 dp:

```jsonc
{
  "op": "cb_sem",
  "estimator": "ML",
  "n": 301, "n_dropped_listwise": 0,
  "converged": true,
  "fit": {
    "chi2": 85.3057, "df": 24, "chi2_p": 0.0, "chi2_df": 3.5544,
    "cfi": 0.9306, "tli": 0.8958,
    "rmsea": 0.0923, "rmsea_ci90": [0.0719, 0.1136],
    "srmr": 0.0652
  },
  "loadings": {"x1": 0.7714, "x2": 0.4240, ...},          // standardized; mirrors outer_loadings
  "reliability": {                                         // mirrors the PLS reliability table
    "visual": {"alpha": 0.626, "cr": 0.6253, "ave": 0.3705, "r_squared": null},
    "dem60":  {"alpha": ...,  "cr": ...,    "ave": ...,    "r_squared": 0.1996}
  },
  "paths": {                                               // "src -> tgt" keys, like PLS
    "ind60 -> dem60": {"beta": 0.4468, "b_unstd": 1.4824, "se": 0.399,
                        "z": 3.715, "p": 0.0002, "hypothesized_sign": "positive"}
  },
  "residual_highlights": [{"pair": "x7-x8", "std_residual": 0.13}],  // ≤ 5
  "warnings": []                                           // heywood_case / two_indicator / df<=0 / small_n
}
```

Notes: `paths` carries `se`/`z`/`p` where PLS carries bootstrap `t`/`ci95` —
same key-shape family, estimator-appropriate cells. `r_squared` lives inside
`reliability` exactly as in the PLS summary (`stats.py:169-177`). Marker-item
loadings report `se: null`. Output size is intrinsically bounded (constructs
× items), no truncation machinery needed beyond the 5-row residual cap.

## 7. Self-validation integration

### 7.1 New adapter: `claims_from_cbsem` + `validate_result("cbsem", ...)`

In `validation.py`, next to `claims_from_ipma` (`validation.py:924-935`), a
`claims_from_cbsem(result, source="computed")` emitting:

- per-item standardized loadings → metric **`loading_cbsem`** (NOT
  `loading`): the soft Heywood bound at `validation.py:147-150` exists for
  exactly this — CB-SEM standardized loadings may legitimately exceed 1 in a
  Heywood solution, which must be a soft finding, not the hard
  `bounds.loading`;
- `alpha`/`cr`/`ave` per construct, table `measurement_model`;
- `r2` per endogenous construct, table `structural_model`;
- `beta` (standardized) per path + the z statistic emitted as a **`t` claim
  with `df=None`** + `p` per path: the existing C3 t↔p check
  (`validation.py:424-461`) computes `p_min = 2·norm.sf(|t|)`, which is
  exactly the z-based p — a correct z/p pair sits at the boundary of the
  allowed band and passes; a fabricated pair still fires;
- fit indices → `cfi`/`tli`/`rmsea`/`srmr`/`chi2_df` claims, table
  `model_fit` (bounds pre-exist at `validation.py:179-191`);
- `n` (table `model_fit`) with the integer flag.

Register kind `"cbsem"` in the `validate_result` dispatch
(`validation.py:938-962`).

### 7.2 Consistency checks extended

- **C1 (AVE ≈ mean λ², hard)** currently groups only metric `"loading"`
  (`validation.py:298-301`). Extend `_by_construct` to treat
  `loading_cbsem` identically — the identity holds for standardized CFA
  loadings, and our AVE is *defined* as mean λ² (§5.2), so computed output is
  exactly consistent and a doctored AVE fires.
- **`chi2_df` bounds branch**: `chi2_df` is in `METRICS`
  (`validation.py:28`) but `_bounds` has no branch for it — add hard `≥ 0`.
- **`rmsea` vs its CI**: new small soft check — when an `rmsea` claim and its
  `rmsea_ci90` values coexist, the point estimate must lie inside the CI
  (containment, mirroring C4's posture at `validation.py:401-414`).

### 7.3 The family-mix fix (required, subtle)

`_PLS_FAMILY = {"ave", "htmt", "gof", "f2", "fornell_larcker_diag", "q2"}`
(`validation.py:488`). **CB-SEM legitimately reports AVE and Fornell–Larcker
— both originate in CB-SEM literature** — so a clean computed `cb_sem`
result emitting `ave` + `cfi` claims would fire `xtable.family_mix`
(`validation.py:514-521`) **on itself**. Fix: narrow the PLS family to the
genuinely PLS-exclusive metrics:

```python
_PLS_FAMILY = {"htmt", "gof", "f2", "q2"}
```

Existing tests stay valid: the submodule mix test
(`libs/thesis-stats/tests/test_validation_xtable.py:19-22`) includes an
`htmt` claim, and the dothesis test
(`agent/tests/test_stats_validation.py:59-62`) injects `cfi` into a PLS
block whose hypothesis tests carry `f2` — both still fire. Verify both, and
add the new positive/negative pair: computed `cb_sem` claims alone → **no**
family-mix; `cb_sem` claims + any `htmt`/`q2`/`f2`/`gof` claim → hard
`xtable.family_mix` (this is the "confirm the check now fires from a
computed source" requirement).

### 7.4 dothesis-side wiring

- `agent/stats_validation.py` `claims_from_run_stats` gains an
  `op == "cb_sem"` branch delegating to
  `thesis_stats.validation.claims_from_cbsem` — mirror the `mga` branch at
  `agent/stats_validation.py:90-92`. The ride-along attach point
  (`agent/tools/stats.py:510-521`) needs **no change**.
- Persisted block: `claims_from_analysis_results` already reads
  `structural_model.{cfi,tli,rmsea,srmr}` (`agent/stats_validation.py:294-297`).
  Two touch-ups: (a) also read `chi2_df` there; (b) when the block carries
  CB-SEM fit indices, emit `measurement_model` item loadings as
  `loading_cbsem` instead of `loading` (`agent/stats_validation.py:240-243`)
  so a persisted Heywood loading is a soft finding, consistent with the
  computed path. The M4 commit gate then blocks/warns through the existing
  path with zero gate-code changes.

## 8. Product integration (advisory, never blocking)

- **`run_stats` docstring** (`agent/tools/stats.py:445-496`): add the
  `cb_sem` entry to the model-based op list.
- **M4 skill** (`skills/dothesis-m4-analysis/SKILL.md`):
  - op list (`SKILL.md:48-88`): add the `cb_sem` bullet — params, what comes
    back, and the three narration rules: (1) report fit against Hu & Bentler
    (1999): CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08 — the same thresholds
    the lavaan parser applies (`orchestrator/tools/m4_parsers/lavaan.py:22-26`);
    (2) a `heywood_case` warning is a respecification signal — never present
    the fit as clean; (3) `residual_covariances` only with theoretical
    justification, and disclose them.
  - family rule (`SKILL.md:36-38`): extend with "if M3's tool is CB-SEM, use
    op `cb_sem` — never `pls_sem` — and report CFI/TLI/RMSEA/SRMR + χ²/df; if
    it is PLS-SEM, never call `cb_sem`." This is the compute-side closure of
    the loop `method_advice` opens (`SKILL.md:71-76`,
    `agent/method_advisor.py:112-120`).
  - screening cross-reference: run `screening` first, same as the existing
    step-1.5 rule.
- **M5 skill**: one line — CB-SEM results chapters quote the computed `fit`
  table and per-construct reliability, same sourcing rule as PLS.
- The lavaan **parser** (`orchestrator/tools/m4_parsers/lavaan.py`) stays —
  parse-and-compute coexist; parsed results remain `source="parsed"`, the
  computed op is `source="computed"` with tighter tolerances
  (`validation.py:32`).

## 9. Testing strategy

### 9.1 Trust anchors (the non-negotiables)

Per the trust-anchor rule (`libs/thesis-stats/README.md:77-92`), every new
statistic ships with an independent reference. Two published lavaan anchors,
both datasets vendored as CSVs into `libs/thesis-stats/tests/fixtures/`
(copied from the canonical distributions; ~301×15 and 75×11 — small), tests
exercising the **public `run_cbsem` path including the syntax mapper**, not
semopy internals:

**Anchor A — Holzinger–Swineford 1939 CFA** (n=301, 3 factors × 3 items,
the lavaan tutorial's `cfa` example). Pinned expected values (published
lavaan output; semopy-under-our-pins agreement verified 2026-07-17):

| Statistic | lavaan published | semopy (verified) | tolerance |
|---|---|---|---|
| χ² | 85.306 | 85.3057 | ±0.01 |
| df | 24 | 24 | exact |
| CFI | 0.931 | 0.93056 | ±0.005 |
| TLI | 0.896 | 0.89584 | ±0.005 |
| RMSEA | 0.092 | 0.09228 | ±0.005 |
| RMSEA 90% CI | [0.071, 0.114] | [0.0719, 0.1136] | ±0.003 each |
| SRMR | 0.065 | 0.0652 | ±0.005 |
| std loadings x1…x9 | .772 .424 .581 .852 .855 .838 .570 .723 .665 | match to 3 dp | ±0.005 each |

**Anchor B — Political Democracy** (n=75, 3 latents, structural paths +
residual covariances — exercises the structural side and the
`residual_covariances` param):

| Statistic | lavaan published | semopy (verified) | tolerance |
|---|---|---|---|
| χ² / df | 38.125 / 35 | 38.125 / 35 | ±0.01 / exact |
| CFI / TLI | 0.995 / 0.993 | 0.9954 / 0.9927 | ±0.005 |
| RMSEA / SRMR | 0.035 / 0.044 | 0.0347 / 0.0445 | ±0.005 |
| dem60~ind60 (unstd, SE, z) | 1.483, 0.399, 3.715 | 1.4824, 0.399, 3.715 | ±0.005 |
| dem65~ind60 / dem65~dem60 (unstd) | 0.572 / 0.837 | 0.5719 / 0.8376 | ±0.005 |
| std paths | 0.447 / 0.182 / 0.885 | match | ±0.005 |
| R²(dem60) ≡ std β² | 0.1996 | identity holds | 1e−6 |

The SRMR and RMSEA-CI rows are the **independent references for the
hand-computed pieces** — they are lavaan's numbers, not semopy's.

**Do not weaken these tolerances to make a change pass** (same rule as the
accuracy suites, `README.md:88`). If a pin bump moves an anchor value, that
is a finding about the bump, not about the tolerance.

### 9.2 Degenerate-input tests

- Heywood fixture (seeded, n=12, near-collinear items — the verified probe
  recipe): result returns with `warnings` containing `heywood_case`, fit
  block present, no exception; `validate_result("cbsem", payload)` yields at
  most soft findings.
- Zero-variance item / n ≤ observed-variable count → typed
  `DataError`/`EstimationError`, clean message, `run_stats` returns
  `{"error": ...}` JSON.
- Non-convergence (force via `fit(..., options={"maxiter": 1})`; if semopy
  does not forward solver options, monkeypatch `SolverResult.success`) →
  `EstimationError`, no numbers in the payload.
- Moderation node / single-indicator construct / unknown estimator /
  unknown residual-covariance column → typed errors with the §5.1/§5.4
  messages.
- semopy absent (simulate with `sys.modules["semopy"] = None` style
  monkeypatch) → `EstimatorUnavailableError` with the §4.3 message; this
  test runs even in envs that have semopy.

### 9.3 Clean-fixture sanity

A seeded 3-construct × 4-item generator (reuse the `make_survey` posture from
the screening tests) with a known 2-path structure: loadings all in
(0.5, 0.95), α/CR ≥ 0.7, AVE ≥ 0.4, both paths recovered with the planted
signs, fit indices finite and in-bounds.

### 9.4 Golden-clean + family-mix

- `validate_result("cbsem", <clean HS39/PD/fixture payloads>)` → **zero
  findings** (mirrors `tests/test_validation_golden.py`). This is what makes
  the §5.2 formula choices load-bearing.
- Doctored payloads: AVE bumped → hard `consistency.ave_loadings` (via the
  extended C1); λ = 1.2 → soft `bounds.loading_heywood`; CFI = 1.3 → hard
  `bounds.cfi`; z/p mismatch → hard `consistency.t_p`.
- Family-mix pair from §7.3 (fires with a PLS-exclusive metric, silent for
  pure CB-SEM); both pre-existing mix tests still green after the
  `_PLS_FAMILY` narrowing.

### 9.5 Determinism + dothesis-side

- Same file + params twice → byte-identical JSON (fresh-`Model`-per-call
  guarantee, §5.3).
- Op tests in `agent/tests/test_stats_tool.py`: whitelist entry present;
  clean run returns the §6.2 keys; validation ride-along attaches on a
  doctored monkeypatched result; error paths return `{"error": ...}` JSON
  (`stats.py:497-509` unchanged).
- `agent/tests/test_stats_validation.py`: the `cb_sem` claims branch; the
  persisted-block `loading_cbsem` switch; commit-gate block/warn via the
  existing path with zero `state_tools.py` changes.

## 10. Risks

1. **semopy compatibility drift** (was the #1 unknown — now measured). The
   exact-pin resolve is verified working today; the extra pins semopy AND its
   two new transitives, so nothing floats. Residual risk: a future core-pin
   bump breaking semopy — covered because the anchors run in the submodule
   suite, which the README already requires after any bump
   (`README.md:74-75`).
2. **Broken code paths inside semopy under numpy 2** (`np.float`/`np.int`,
   §4.1.4). Mitigated by the never-call list and by the wrapper exposing
   only `Model`/`calc_stats`/`inspect`-derived results.
3. **Self-firing family-mix** (§7.3). Would have made every clean CB-SEM run
   report a hard finding; fixed by narrowing `_PLS_FAMILY`, guarded by the
   golden-clean test.
4. **Boundary Heywood is silent in semopy** (variances clamp to 0 without
   any flag — verified). Mitigated by explicit boundary detection (§5.4);
   the tripwire is the Heywood fixture test.
5. **SRMR formula variants** (lavaan has several; ours matches lavaan's
   default for complete-data ML). Anchored on two datasets to ±0.005; if a
   consumer later needs `srmr_bentler`-style variants, they are new
   statistics and need their own anchors.
