# Data Screening & Preparation Ops — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-data-screening-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #3 in `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:113-139` (Phase 1, "Data screening & preparation ops + auto-generated cleaning section")
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md` §3.4 (:129-139 — the automatic screening report + generated data-cleaning section), gap list (:74 "No missing-data (MCAR/imputation), Mahalanobis outliers, or straight-lining"), limitations seeding (:171), checklist item (:275-276 "Data screening is documented with computed numbers")
**Builds on:** `2026-07-17-thesis-stats-shared-lib-design.md` (shipped), `2026-07-17-stats-self-validation-design.md` (shipped — the claims/findings machinery this spec extends), `2026-07-17-power-analysis-design.md` (shipped — the pure-module + op + validation-adapter pattern this spec repeats)

---

## 1. Motivation

Real survey data arrives dirty, and every committee expects a screening
narrative in Chapter 3. Today the compute layer starts at the measurement
model:

- **Nothing screens.** `rigor.py` covers assumptions/effect sizes/CMB only
  (`libs/thesis-stats/src/thesis_stats/rigor.py:1-7`); no missingness
  profile, no Little's MCAR, no Mahalanobis, no careless-response detection,
  no reverse-coding application anywhere in the engine (grep-verified;
  also the engine README's own deferred-roadmap entry,
  `libs/thesis-stats/README.md:89-92`).
- **Missing data is handled silently and inconsistently.** The ported
  analyzers drop rows listwise in descriptives/EFA
  (`libs/thesis-stats/src/thesis_stats/spss.py:180,209,257`) but **silently
  mean-impute** in the regression path (`spss.py:389`
  `fillna(df[...].mean())`). The student never learns which treatment was
  applied, and cannot defend it.
- **Plans exist; nothing executes them.** The M3→M4 preflight only asks
  whether a `missing_data_plan` string exists (`agent/preflight.py:40-41`)
  and whether any instrument item is flagged `reverse_coded`
  (`agent/preflight.py:36-37`). The instrument schema already carries the
  per-item `reverse_coded` flag (`agent/tools/instrument.py:88`), but no code
  ever recodes the uploaded data with it.
- **Careless responding is only *suspected* after the fact.**
  `check_thresholds` flags "all loadings > 0.9 ⇒ possible straight-lined
  data" (`agent/tools/stats.py:337-339`) — a post-hoc symptom, not a
  detection on the raw rows.
- The vision names the exact deliverable: an on-upload screening report and a
  generated data-cleaning section — *"of 260 responses, 14 removed for
  straight-lining, 6 multivariate outliers (Mahalanobis p<.001), missingness
  MCAR (p=.42), mean imputation applied…"* — every number computed
  (`...vision.md:133-139`).

This initiative adds **deterministic data screening** (no LLM anywhere) over
the RAW uploaded data: a pure `screening.py` module in `thesis-stats`, a
whitelisted `run_stats` op, self-validation coverage for the new numbers, and
the M4/M5/preflight wiring that turns the output into a committee-ready
"data screening & cleaning" narrative.

## 2. Scope and non-scope

**In scope**

- Pure module `libs/thesis-stats/src/thesis_stats/screening.py`: missingness
  profile + Little's MCAR test (own EM implementation — §4.1), univariate +
  Mahalanobis outliers (§4.2), careless/insufficient-effort detection (§4.3),
  reverse-coded item audit + recode (§4.4), a deterministic recommendation
  engine and narrative builder (§4.5), a `run_screening(...)` dispatcher and
  an `apply_screening(...)` transformer (§5).
- A whitelisted `run_stats` op `screening` in `agent/tools/stats.py`, with
  explicit-only derived-file application (§6).
- Self-validation coverage: new metric bounds, a `claims_from_screening`
  adapter, a screening count-consistency check, golden-clean tests (§7).
- Product integration: M4 pipeline step + persisted
  `analysis_results.data_screening` block (commit-gate covered), preflight
  item upgrade, M4/M5 skill copy (§8). All **advisory** — screening never
  blocks an analysis (vision principle 4); only the existing hard-findings
  commit gate blocks, and only for impossible numbers.

**Out of scope (explicitly deferred)**

- **Imputation beyond mean/listwise as an applied transform.** Regression/EM
  imputation, multiple imputation (statsmodels MICE), and FIML are
  *recommendation outputs only* in v1 (§4.5); FIML is an estimator property
  (CB-SEM, roadmap initiative #9), not a data transform. Recommending them is
  the committee-facing job; applying them is a later increment.
- **Attention-check item consumption** — needs instrument intelligence
  (roadmap initiative #13, `...roadmap.md:373-393`) to generate/mark those
  items first. The `reverse_items` param (§6) is the v1 hook.
- **Response-time / speeding detection** — the upload has no timing metadata
  today (roadmap :128 mentions "speeding proxies"; without per-row duration
  columns there is nothing deterministic to compute; if a `duration` column
  is present the careless check reports its distribution, nothing more).
- **An M5 renderer change.** The narrative (§4.5) is designed to be quoted
  verbatim by Chapter 3, exactly like the power op's `justification` sentence
  is quoted today (`2026-07-17-power-analysis-design.md` §6); M5 gets one
  skill sentence (§8.5), no renderer code.
- The headless orchestrator path — same deferral and reason as the power
  spec (`2026-07-17-power-analysis-design.md` §2): wiring waits for the
  headless/interactive convergence work.
- Any LLM involvement, any new dependency. Everything is pandas/numpy/scipy
  (+ nothing else), all already pinned (`libs/thesis-stats/pyproject.toml:20-27`).

## 3. Placement decision

| Option | Verdict |
|---|---|
| (a) Compute in `agent/tools/stats.py` only | Rejected — fillform (the other thesis-stats consumer, `libs/thesis-stats/README.md:3-4,49-56`) needs the same screening; the math must be unit-tested against numpy/scipy next to the engine, not inside a LangChain tool module. |
| (b) Fold into `run_rigor` as new checks | Rejected — rigor checks are *assumption* tests on presumed-clean data (`rigor.py:173-237`); screening is the step that *produces* clean data and has its own params (Likert range, reverse keys, apply-decisions) and its own committee section. Mixing them would bloat one op's payload past the bounded-summary rule and blur "is my data usable" with "does my data meet test assumptions". They stay siblings in the rigor family. |
| **(c) New pure `screening.py` in `thesis-stats` + a dedicated `run_stats` op `screening`** | **Chosen.** Mirrors the shipped layering exactly (power did the same): pure functions in the submodule (seeded-fixture tested), a thin whitelisted data-touching op (lazy import, bounded summary, fail-open validation ride-along — `agent/tools/stats.py:119-127,400-411`), and product wiring that consumes the output. |

**Op name:** `screening` (not the roadmap sketch's `screen`,
`...roadmap.md:124`) — noun form matches the module name and reads correctly
in the whitelist next to `rigor`/`power` (`agent/tools/stats.py:277-293`).
The roadmap wording is a sketch; this spec is authoritative.

Concretely:

- **`libs/thesis-stats/src/thesis_stats/screening.py`** (new) owns all math
  and the narrative templates. Exported from `thesis_stats/__init__.py`
  (alongside `run_power`, `__init__.py:26,44`); `__version__` bumps `0.3.0`
  → `0.4.0` (`__init__.py:36`).
- **`agent/tools/stats.py`** gains `_op_screening` + a `"screening"` entry in
  `OPS` (`stats.py:277-293`), following the thesis-stats-backed op pattern
  (`stats.py:248-256` `_op_rigor` is the closest sibling: data-touching,
  lazy import, `_round_floats` bounding).
- **Submodule workflow** (`libs/thesis-stats/README.md:62-64`): edit under
  `libs/thesis-stats/`, commit + push inside the submodule, then
  `git add libs/thesis-stats` in the parent to bump the pointer.

## 4. Checks — methods and formulas

Everything below is deterministic: same file + params in → same JSON out. No
RNG anywhere (Mahalanobis, MCAR-EM, longstring are all closed computations).
Column scope: the union of `measurement` item columns when a measurement map
is given (the same convention as `rigor.py:158-168` `_measurement_items`),
else all numeric columns (`rigor.py:29-30`). Row identity: 0-based positional
row index of the loaded frame (stable across `_load_df` re-reads of the same
file, `stats.py:21-32`).

### 4.1 Missing data (`check="missing"`)

**Profile (always computed):**

- per-variable: `missing_n`, `missing_pct` (0–100, 2 dp);
- overall: `overall_missing_pct` (missing cells / total cells), `n_rows`,
  `n_complete_cases`, `n_patterns` (distinct missingness patterns);
- **range violations** rider: when `likert_min`/`likert_max` are given (or
  inferred, §6), count per-item values outside `[likert_min, likert_max]` —
  a data-entry error signal committees do ask about. Reported as
  `out_of_range: {item: count}` (only offending items listed).

**Little's MCAR test — own implementation, verified gap.** statsmodels
0.14.5 (the pinned version, `libs/thesis-stats/pyproject.toml:23`) has **no
Little's MCAR test** — `statsmodels/imputation/` contains only `bayes_mi`,
`mice`, `ros` (verified against the repo's installed venv 2026-07-17). No
other pinned dependency has it. So `screening.py` implements Little (1988)
directly — it is ~80 lines of numpy/scipy and fully testable:

1. Partition the rows into J distinct missingness patterns; drop
   fully-missing rows (counted, reported).
2. Estimate the MVN mean vector μ̂ and covariance Σ̂ by **EM** (E-step:
   per-pattern conditional expectations of the missing block given the
   observed block using the current μ, Σ — the standard regression/sweep
   update; M-step: recompute μ, Σ from the completed sufficient statistics;
   init from available-case means and variances; tolerance 1e-5 on the max
   parameter change, max 200 iterations).
3. Test statistic
   `d² = Σ_j n_j (ȳ_obs,j − μ̂_obs,j)ᵀ Σ̂_obs,j⁻¹ (ȳ_obs,j − μ̂_obs,j)`
   over patterns j, where `ȳ_obs,j` is the observed-variable mean vector of
   pattern j;
4. `df = (Σ_j p_j) − p` (p_j = #observed variables in pattern j, p = total
   variables); `p_value = χ²_df.sf(d²)` (scipy).

Output: `mcar: {chi2, df, p, n_patterns, method: "Little (1988), EM ML
estimates", interpretation}` where interpretation is the deterministic
sentence "p ≥ .05 → consistent with MCAR" / "p < .05 → MCAR rejected —
missingness is systematic".

**Guards (skip with a reason, never a wrong number — the `run_rigor`
advisory-skip posture, `rigor.py:173-237`):** no missing data → `status:
"not_applicable"`; only one pattern with missing → df = 0 → skipped;
`n_rows ≤ n_vars + 5` or EM non-convergence or singular `Σ̂_obs` (pseudo-
inverse condition check) → `status: "skipped", reason: ...` and the
recommendation engine falls back to percentage-threshold rules only (§4.5).
Variable cap: when > 50 columns are in scope, run the MCAR test on the
measurement items only (or the 50 highest-missingness columns if no map),
disclosed in the output.

### 4.2 Outliers (`check="outliers"`)

**Univariate** (mainly for continuous demographics; the narrative notes that
bounded Likert items rarely produce meaningful z-outliers):

- z-rule: |z| ≥ 3.29 (two-tailed p < .001, Tabachnick & Fidell) per variable;
- IQR rule: outside `[Q1 − 3.0·IQR, Q3 + 3.0·IQR]` (extreme fence; the 1.5
  mild fence is reported as a count only).
- Output per variable: counts; plus one capped list of unique flagged row
  indices across variables.

**Multivariate — Mahalanobis D²** (the committee ritual):

- Computed over the measurement-item columns (or `columns` param), complete
  cases only (`excluded_incomplete_n` reported);
- `D²_i = (x_i − x̄)ᵀ S⁻¹ (x_i − x̄)` with the sample covariance S
  (`ddof=1`); singular S → pseudo-inverse + a `warnings` entry;
- Cutoff: `χ²(df=k).ppf(1 − 0.001)` — p < .001, the Tabachnick & Fidell
  convention (`alpha` overridable via `thresholds`, §6);
- Output: `{k, cutoff, alpha: 0.001, flagged_n, flagged_indices: [...capped],
  max_d2, method: "Mahalanobis distance, χ² cutoff p < .001"}`.
- Guard: needs `n_rows > k + 1`; otherwise skipped with reason.

**Bounding rule (hard):** every flagged-index list is capped at 50 entries
with `truncated: true` and the full count alongside — indices, counts and
percentages only, **never row contents** (the same never-row-level rule as
the PLS summarizer, `stats.py:119-127`).

### 4.3 Careless / insufficient-effort responses (`check="careless"`)

Over the Likert measurement items (requires ≥ 3 item columns; else skipped):

- **Intra-individual SD (invariability):** per-row SD across items; rows
  with SD ≤ 0.05 (default; effectively "answered everything identically")
  are flagged straight-liners. When `reverse_items` are declared, the
  narrative strengthens the claim: a truly consistent respondent *cannot*
  flat-line across mixed-keyed items.
- **Longstring:** per-row longest run of identical consecutive answers (in
  file column order, disclosed as such); rows whose longstring equals the
  full item count are flagged (they coincide with SD=0 by construction —
  reported separately because committees know the term); the distribution
  (`max`, `p95`) is reported for context.
- Output: `{flagged_n, flagged_indices: [...capped], intra_sd_threshold,
  longstring: {max, p95}, method}`.

Deliberately simple v1: psychometric-synonym indices (even-odd consistency,
person-total correlation) are deferred to initiative #13 when attention-check
items exist to anchor them.

### 4.4 Reverse-coded items (`check="reverse_coded"`)

Given `measurement` (construct → item columns) and Likert bounds:

- **Declared mode** (`reverse_items` given — sourced from the M3 instrument's
  per-item `reverse_coded` flags, `agent/tools/instrument.py:88`): for each
  declared item compute the corrected item-total correlation `r_it` (item vs
  the mean of the *other* items of its construct):
  - `r_it < 0` → `needs_recoding` with the recode formula
    `value → (likert_min + likert_max − value)`;
  - `r_it ≥ 0` → `appears_already_recoded` warning (recoding again would
    corrupt the data — the double-recode hazard, §10) — **not** recoded on
    apply.
- **Auto-detect mode** (no `reverse_items`): any item with
  `r_it ≤ −0.10` is listed under `suspected_reverse_keyed` (soft language —
  detection only, never auto-recoded; the agent asks the student to confirm
  against the questionnaire).
- Output: `{declared: [...], needs_recoding: [...], appears_already_recoded:
  [...], suspected_reverse_keyed: [...], recode_formula:
  "value -> (min + max − value)", likert_min, likert_max, item_total_r:
  {item: r}}`.

### 4.5 Recommendation engine + committee narrative (always computed)

**Missing-data recommendation** — deterministic decision rules with the
citations a committee expects (structure mirrors the power op's
justification/citations fields, `power.py:222-234,237-265`):

| Condition | Recommendation |
|---|---|
| No missing data | `none` — "complete data; no treatment required." |
| overall < 5% AND MCAR not rejected (p ≥ .05) | `listwise` — defensible and simplest (Little 1988; Hair et al. 2017: < 5% ignorable); `mean` noted as acceptable-but-variance-attenuating alternative. |
| overall < 10% AND MCAR not rejected | `listwise` if `n_complete ≥` any persisted power target, else `mean` with the attenuation caveat (Tabachnick & Fidell). |
| MCAR rejected (p < .05) | `fiml_or_multiple_imputation` — listwise would bias; recommend FIML (CB-SEM estimator) or regression/multiple imputation, with the honest note that v1 applies neither (§2) and the student should disclose the pattern. |
| MCAR test skipped | percentage-threshold rules only, disclosed. |
| any variable > 15% | additional flag: consider dropping the item/case (Hair et al. 2017), listed per variable. |

Emitted as `{strategy, alternatives, rationale, citations}` — never applied
without §6's explicit `apply`.

**The narrative** — a deterministic sentence set (built from templates, no
LLM) that M4 persists and M5's Chapter 3 quotes verbatim; matches the vision
example (`...vision.md:137-139`). Two registers, both returned:

- `narrative` (report-only run): *"Of 260 responses, screening identified 14
  straight-lined cases (intra-individual SD ≈ 0), 6 multivariate outliers
  (Mahalanobis D², χ²(18) cutoff at p < .001), and 1.8% missing data
  overall; Little's MCAR test was non-significant (χ²(41) = 44.2, p = .34),
  consistent with data missing completely at random. Recommended treatment:
  listwise deletion (final N = 240). Items JS3 and OC2 are reverse-keyed and
  require recoding prior to analysis."*
- `narrative_applied` (only present after an `apply` run): the past-tense
  variant ("…were removed… mean imputation was applied… were recoded…"),
  with n before/after per stage.

Sentence templates are per-check and compose only from computed fields; a
skipped check contributes its skip reason ("Little's MCAR test could not be
computed (singular covariance); treatment was selected on missingness
percentages alone.").

`citations`: Little (1988); Tabachnick & Fidell (2013); Hair, Hult, Ringle &
Sarstedt (2017); Curran (2016) for careless responding — returned as a list
like `power.py:223-228`.

## 5. Pure API (`thesis_stats/screening.py`)

```python
run_screening(
    data,                        # list[dict] | DataFrame (DataLike, rigor.py:20-26)
    *,
    checks: list[str] | None = None,   # subset of {"missing","outliers","careless","reverse_coded"}; None = all applicable
    measurement: dict[str, list[str]] | None = None,  # construct -> item columns (model_adapter convention)
    likert_min: float | None = None,   # None -> inferred (min/max observed over items, disclosed)
    likert_max: float | None = None,
    reverse_items: list[str] | None = None,
    group: str | None = None,          # optional: per-group n + missingness in the profile
    thresholds: dict | None = None,    # overrides: {mahalanobis_alpha, z_cut, iqr_k, intra_sd, item_total_r}
) -> dict

apply_screening(
    data,
    plan: dict,   # {"recode_reverse": [items], "drop_rows": [indices] | {"careless": [...], "outliers": [...]},
                  #  "missing": "listwise" | "mean" | None}
) -> tuple[DataFrame, dict]   # (cleaned frame, applied-summary with per-stage n accounting)
```

Behavior rules:

- **Pure and deterministic** — no I/O, no RNG, no LLM; same inputs → same
  output. JSON-serializable dicts throughout (floats 4 dp, percentages 2 dp).
- Inapplicable checks **skip into `warnings`, never raise** — the exact
  `run_rigor` composer posture (`rigor.py:173-237`). Genuinely unusable
  input (empty data, unknown check name, `likert_min ≥ likert_max`) raises
  `ValueError` with a plain message; the op layer converts to the standard
  `{"error": ...}` JSON (`stats.py:393-399`).
- Fixed order inside `apply_screening` (documented, so n-accounting is
  reproducible): **1)** recode reverse items → **2)** drop careless rows →
  **3)** drop outlier rows → **4)** missing treatment (listwise drop or mean
  impute). Only `listwise`/`mean` are appliable (§2); anything else in
  `plan.missing` raises. The applied-summary reports
  `{n_before, after_careless, after_outliers, n_after, recoded: [...],
  imputed_cells}` — every number the narrative and the validator (§7)
  reconcile.
- `run_screening` output shape (top level):

```json
{
  "n_rows": 260, "columns_scoped": 18, "scope": "measurement_items",
  "likert": {"min": 1, "max": 5, "source": "declared"},
  "missing": { ...§4.1... },
  "outliers": { ...§4.2... },
  "careless": { ...§4.3... },
  "reverse_coded": { ...§4.4... },
  "recommendation": {"strategy": "listwise", "alternatives": ["mean"], "rationale": "...", "citations": [...]},
  "narrative": "...", "warnings": [...]
}
```

## 6. The `run_stats` op contract

`run_stats(op="screening", file, params={...})` — params mirror §5:
`checks`, `measurement`, `likert_min`, `likert_max`, `reverse_items`,
`group`, `thresholds`, plus the op-only `apply`.

- **Data-touching, like `rigor`:** loads via `_load_df` (csv/xlsx/.sav,
  `stats.py:21-32`), converts with `_records`/DataFrame directly, lazy
  `import thesis_stats` inside `_op_screening` so a missing install degrades
  to the existing "stats dependency missing" JSON (`stats.py:395-396`).
- `measurement` uses the same construct→columns convention the model-based
  ops document (`stats.py:362-366`; `agent/tools/model_adapter.py:14`). When
  the caller has a `conceptual_model` instead, the agent passes the
  measurement map it already derived for the other ops — the op itself does
  NOT take a conceptual_model (screening needs columns, not paths).
- Likert bounds: declared params win; else inferred from the observed
  min/max across scoped items with `"source": "inferred"` in the payload and
  a warning (inference assumes the sample used the full scale).
- **Bounded output, no raw rows** (hard rule): the §5 payload passed through
  `_round_floats` (`stats.py:130-137`); flagged-index lists already capped
  at 50 (§4.2); per-variable tables capped at 100 variables (beyond that:
  the 20 worst by missingness + an aggregate count).

**Explicit-only application (`params.apply`) — the no-silent-imputation
rule.** A plain `run_stats(op="screening", ...)` call is **report-only**: it
mutates nothing and recommends. Only when the student has confirmed the
treatment does the agent pass:

```json
"apply": {"recode_reverse": true, "drop_careless": true,
          "drop_outliers": true, "missing": "listwise"}
```

Then `_op_screening` re-runs the checks, builds the `apply_screening` plan
from its own flagged sets (`recode_reverse: true` → the `needs_recoding`
list only — never `appears_already_recoded` items), writes the cleaned frame
as **`<stem>_screened.csv` next to the source file** (workspace-local —
in-process today, sandbox-safe in production per `stats.py:1-8`; always CSV
regardless of input format), and returns the §5 payload plus:

```json
"applied": {"derived_file": ".../data_screened.csv", "n_before": 260,
            "after_careless": 246, "after_outliers": 240, "n_after": 240,
            "recoded": ["JS3", "OC2"], "imputed_cells": 0,
            "missing_strategy": "listwise"},
"narrative_applied": "..."
```

Downstream ops then run on `derived_file` — the roadmap's "every downstream
op runs on the cleaned derivative with the screening provenance attached"
(`...roadmap.md:133-138`); the M4 skill instructs this (§8.4). Re-running
apply overwrites the derived file deterministically (idempotent: recode
skips items whose `r_it` already flipped positive — the §4.4 guard).

### `run_stats` docstring

The op list in the `run_stats` docstring (`stats.py:352-386`) gains:

```
screening — data screening on the RAW upload: missingness % + Little's MCAR
            + recommended treatment, univariate/Mahalanobis outliers,
            straight-lining/careless rows, reverse-coded item audit, and a
            committee-ready cleaning narrative (params: checks=[...],
            measurement, likert_min/likert_max, reverse_items, group,
            apply={...} ONLY after the student confirms treatment — a plain
            call never modifies data). Run it between detect and the outline.
```

## 7. Self-validation integration

The shipped validation layer treats a bad screening number like any other
bad statistic (same recipe as power, `2026-07-17-power-analysis-design.md`
§7):

1. **Metric registry** (`libs/thesis-stats/src/thesis_stats/validation.py:24-30`):
   add `"missing_pct"` and `"mahalanobis_d2"` (`p`, `n`, `df` already exist).
2. **Bounds checks** (`validation.py:110-212` `_bounds`):
   - `missing_pct` ∈ [0, 100] → outside is **hard** (`bounds.missing_pct`);
   - `mahalanobis_d2` < 0 → **hard**; when the claim carries `n`,
     `d² > (n−1)²/n` (the algebraic maximum of a sample Mahalanobis
     distance) → **hard** (`bounds.mahalanobis_d2`);
   - the MCAR `p` and `chi2` (as `variance`-style ≥ 0 via a `chi2` reuse of
     the existing non-negativity pattern) ride the existing `p`/bounds
     machinery (`validation.py:154-156`).
3. **Count-consistency check** (new, in the `_consistency` family,
   `validation.py:298-302`): claims in `table="screening"` carry role flags
   (`{"role": "n_before"}`, `{"role": "n_after"}`, `{"role": "removed"}`).
   Check `consistency.screening_counts`: `n_after = n_before − Σ removed −
   listwise_dropped` (exact integers → **hard** on mismatch), and every
   flagged/removed count ≤ n_before (**hard**).
4. **Adapter** — `claims_from_screening(result)` in `validation.py`
   (engine-native, next to `claims_from_rigor` at `validation.py:712-728`):
   emits per-variable `missing_pct` claims (capped at the payload's own
   bounded table), the MCAR `p` (flagged `is_p`) and `df`, `mahalanobis_d2`
   for `max_d2` with `n`, the count claims with role flags, and — when
   `applied` is present — the n-accounting claims. Registered in
   `validate_result` dispatch (`validation.py:851-868`) under kind
   `"screening"`.
5. **Dothesis side** — `claims_from_run_stats`
   (`agent/stats_validation.py:55-87`) gains an `op == "screening"` branch
   delegating to `claims_from_screening` (mirroring the `power` branch at
   `:84-86`). The existing fail-open attach in `run_stats`
   (`stats.py:400-411`) then covers the new op with zero further wiring.
6. **Persisted-block coverage** — `claims_from_analysis_results`
   (`agent/stats_validation.py:202-280`) gains a `data_screening` branch
   (§8.2 shape → the same claims as 4), so the M4 commit gate
   (`agent/tools/state_tools.py:105-127`, the `stats_validation_failed`
   path) blocks a hand-mutated screening block (e.g. a typed
   `missing_pct: 180` or an n_after that doesn't reconcile) exactly like a
   hard-bad loading.

Rationale for the coverage shape: as with power, the validator's job is not
re-deriving the math (`screening.py`'s own tests do that) but catching
**mutated, mis-persisted, or hand-typed** payloads before they reach
Chapter 3. Golden-clean tests (§9.3) pin that clean screening output yields
zero findings.

## 8. Product integration (advisory, never blocking)

### 8.1 M4 pipeline — "screen before you model"

`skills/dothesis-m4-analysis/SKILL.md` pipeline (`SKILL.md:85-92`) gains a
step between detect and the outline (the roadmap's "0.5 — screen before you
model", `...roadmap.md:135`):

```
1. detect data type from upload            → run_stats(op="detect")
1.5 screen the raw data                    → run_stats(op="screening")  [report-only first]
2. propose analysis outline                → ...
```

Skill rules for the step:

- Run report-only screening right after detect, passing `measurement` (from
  the M3 model / detect step) and `reverse_items` (from the M3 instrument's
  `reverse_coded` flags). Show the narrative + the recommendation; **ask the
  student to confirm the treatment** before any `apply` call — never
  silently impute or drop (the §6 rule, stated in the skill).
- After an applied run, **every subsequent op uses `applied.derived_file`**,
  and the screening payload is persisted (§8.2) before the measurement
  model is run.
- Screening findings are advisory: a rejected MCAR or 30 flagged rows never
  refuses the analysis — it changes the narrative and the limitations.

### 8.2 Persisted `analysis_results.data_screening` block

The M4 results-block contract (`SKILL.md:130-152`) gains a sibling of
`descriptives`:

```json
"data_screening": {
  "n_before": 260, "n_after": 240,
  "missing": {"overall_pct": 1.8, "mcar": {"chi2": 44.2, "df": 41, "p": 0.34},
              "treatment": "listwise"},
  "outliers": {"multivariate_flagged": 6, "removed": 6,
               "method": "Mahalanobis, χ²(18) p<.001"},
  "careless": {"flagged": 14, "removed": 14, "method": "intra-individual SD ≈ 0"},
  "reverse_coded": {"recoded": ["JS3", "OC2"]},
  "narrative": "<narrative_applied or narrative, verbatim from run_stats>"
}
```

Every value is copied verbatim from the op payload (the skill's existing
"never typed from memory" rule, `SKILL.md:134-135`); the commit gate covers
it via §7.6. `descriptives.n` (`SKILL.md:133`) is documented to be the
**post-screening** n, matching `n_after` — the X1 n-consistency check
(`validation.py:480-494`) then keeps every later table honest about it.

### 8.3 Preflight — plan item points at the computed answer

`agent/preflight.py:40-41` message upgrade (advisory strings only, same
pattern as the power upgrade `2026-07-17-power-analysis-design.md` §8.2):

- No `missing_data_plan` → `"No missing-data handling plan — the screening
  op (run_stats op=screening) computes missingness + Little's MCAR and
  recommends a defensible treatment in M4."`
- The reverse-coded item (`preflight.py:36-37`) keeps its wording (design-
  time concern) — no change.

The rubric's `preflight_dimension` reuses the same pure function, so the
wording rides along with zero rubric changes (same free-ride as power §8.3).

### 8.4 M4/M5 skill copy

- **M4** (`skills/dothesis-m4-analysis/SKILL.md`): the op list (`:42-71`)
  gains the §6 `screening` entry; the pipeline gains step 1.5 (§8.1); the
  results-block section gains `data_screening` (§8.2); the "What you do NOT
  do" list gains "❌ Do not apply imputation, drop rows, or recode items
  without an explicit confirmed `apply` — report-only first, always."
- **M5** (`skills/dothesis-m5-writing/SKILL.md`): one rule — Chapter 3's
  data-collection/screening passage quotes
  `analysis_results.data_screening.narrative` verbatim (numbers never
  re-typed), the same quoting discipline as the power `justification`.

## 9. Testing strategy

All engine tests use **seeded fixtures** (`numpy.random.default_rng(42)`) in
`libs/thesis-stats/tests/test_screening.py` + a shared builder in the tests
(pattern: `tests/conftest.py`): a clean 200×12 Likert(1–5) survey of 3
constructs, into which each case injects a known defect.

### 9.1 Known-value / known-count tests

| Case | Fixture | Expected |
|---|---|---|
| Missingness profile | punch 37 MCAR holes in known cells | exact per-variable counts/pcts; `overall_missing_pct` exact; `n_complete_cases` exact |
| Little's MCAR, MCAR data | random mask, seeded | `p ≥ 0.05`; deterministic χ²/df captured once as golden values |
| Little's MCAR, MNAR data | delete a variable's top-quartile values | `p < 0.001` |
| MCAR df formula | hand-built 2-pattern frame | `df == (Σ p_j) − p`, hand-computed |
| EM sanity | MCAR fixture | `μ̂` within ±0.1 of the complete-data means |
| Mahalanobis | plant 4 rows at ~8 SD | exactly those 4 indices flagged; `max_d2` matches a manual numpy computation; `d2 ≤ (n−1)²/n` |
| Univariate z/IQR | plant one 10-SD value in a continuous column | that row flagged, counts exact |
| Careless | plant 7 constant rows | `flagged_n == 7`, exact indices; longstring == item count for them |
| Reverse declared | negate one item (6 − x) | `r_it < 0` → `needs_recoding`; after recode `r_it > 0` |
| Reverse already-recoded | declare a normal item as reverse | `appears_already_recoded`, NOT recoded on apply |
| Auto-detect | no `reverse_items` | the negated item lands in `suspected_reverse_keyed`; clean items don't |
| Recode formula | apply on Likert 1–5 | value v becomes 6 − v, exactly |
| Apply accounting | all defects at once | `n_after == n_before − careless − outliers − listwise_dropped`, per-stage numbers exact; narrative_applied contains each count |
| Recommendation matrix | parameterized over §4.5 rows | each condition → the mapped strategy + citations non-empty |
| Narrative | the combined fixture | contains every count and the MCAR p; report-only uses "identified/recommended", applied uses past tense |

### 9.2 Edge/contract tests

Empty data / unknown check / `likert_min ≥ likert_max` → `ValueError`;
zero-variance column → excluded from Mahalanobis/MCAR with a warning, never
a crash; singular covariance (duplicate column) → MCAR skipped with reason,
Mahalanobis falls back to pinv + warning; < 3 items → careless skipped;
n ≤ k+1 → Mahalanobis skipped; fully-missing rows dropped and counted;
determinism (two identical calls → identical dicts); every payload
`json.dumps`-serializable; every flagged list ≤ 50 with `truncated` set
when clipped; inferred Likert bounds disclosed with `source: "inferred"`.

### 9.3 Validation-layer tests

`missing_pct` = 180 → hard `bounds.missing_pct`; `mahalanobis_d2` = −2 →
hard; `d2 > (n−1)²/n` → hard; screening counts that don't reconcile
(`n_after ≠ n_before − removed`) → hard `consistency.screening_counts`;
removed > n_before → hard. **Golden-clean:** `claims_from_screening` over
`run_screening` on the clean fixture (and on the applied run) →
`validate_claims` yields **zero findings** (mirrors
`tests/test_validation_golden.py`).

### 9.4 Dothesis-side tests

`agent/tests/test_stats_tool.py` (extend): op JSON contract on a fixture CSV
(report-only → no file written, no `applied` key); `apply` → derived
`_screened.csv` exists next to the source with the expected row count, and
the payload's `applied.n_after` matches the file; bad params → `{"error"}`
JSON; validation ride-along (monkeypatched impossible payload → `validation.
hard ≥ 1`). `agent/tests/test_stats_validation.py` (extend): the
`op == "screening"` branch; `claims_from_analysis_results` over a
`data_screening` block (clean → no findings; mutated `n_after` → hard).
`agent/tests/test_state_tools.py` (extend): a commit with a hard-bad
`data_screening` block → `stats_validation_failed`. Preflight message tests
wherever `preflight_check` is covered.

## 10. Risks

1. **Little's MCAR EM correctness — the #1 risk.** No pinned dependency has
   a reference implementation to diff against, and survey data (discrete
   Likert, near-singular item blocks) is exactly where EM gets numerically
   fragile. Mitigated by: the hand-computed df test, the MCAR-vs-MNAR
   discrimination tests, the EM-sanity test against complete-data means, the
   golden-pinned χ²/p values on the seeded fixture, and the hard rule that
   any numerical trouble (non-convergence, singular Σ̂_obs, n too small)
   yields `status: "skipped"` with a reason — a skipped test plus
   percentage-threshold recommendations is defensible; a wrong p-value is
   not.
2. **Silent-mutation regressions.** The whole design rides on report-only
   being the default; a future "helpful" change that auto-applies would
   recreate the `spss.py:389` silent-mean-impute problem one layer up.
   Mitigated by: the op-level test asserting a plain call writes no file,
   the M4 skill's explicit-confirmation rule (§8.1), and the "What you do
   NOT do" entry (§8.4).
3. **Double-recode corruption.** Recoding an already-recoded item destroys
   the data invisibly. Mitigated by the `r_it ≥ 0 → appears_already_recoded`
   guard (§4.4), apply skipping those items, and the idempotence test.
4. **Downstream ops ignoring the derived file.** The cleaned frame only
   matters if `pls_sem`/`efa`/etc. run on it. v1 relies on the skill rule
   (§8.1) + the X1 n-consistency check (`validation.py:480-494`), which
   fires a finding when a later table's n silently reverts to the
   pre-screening count. A run-context "active file" mechanism is a possible
   follow-up, out of scope here.
5. **Index-list privacy/size.** Row indices are metadata, not data, but
   unbounded lists on a 5,000-row upload would blow the bounded-summary
   contract — hence the hard 50-cap with `truncated` (§4.2), tested (§9.2).
6. **Threshold arguments.** Committees vary (p < .001 vs .005 for
   Mahalanobis; 3.29 vs 3.0 for z). Defaults follow the dominant textbook
   conventions (Tabachnick & Fidell; Hair) and every threshold is disclosed
   in the payload and overridable via `params.thresholds` (§5) — the number
   is never presented without its rule.
