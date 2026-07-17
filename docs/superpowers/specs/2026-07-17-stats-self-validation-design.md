# Stats Self-Validation Layer — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-stats-self-validation-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #1 in `2026-07-17-dothesis-vertical-agent-roadmap.md` (Phase 1, "THE #1 NEXT INITIATIVE")
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md` §3.5(1) (self-validation), §4(1) (verified-numbers chain), §5 principles 1–4, checklist item 7
**Builds on:** `2026-07-17-thesis-stats-shared-lib-design.md` (shipped)

---

## 1. Motivation

The product's moat is the verified-numbers chain (vision §4.1):

```
raw data → whitelisted compute → [THIS LAYER] → structured persisted results → rendered tables → coherence-checked prose
```

Today the chain has a hole between "compute" and "persist". `run_stats`
(`agent/tools/stats.py:325`) computes real numbers, but nothing checks them
before the agent narrates or commits them: a degenerate bootstrap, collinear
indicators producing an AVE inconsistent with its own loadings, or a
pathological fit yielding R² outside [0,1] flows straight into
`analysis_results` (owned by M4 — `agent/state.py:49`) and then into
Chapter 4. The pasted-upload path is worse: the m4 parsers
(`orchestrator/tools/m4_parsers/`), the export/vision parsers
(`agent/tools/output_parse.py`), and the student's own typing can all deliver
mis-parsed or mistyped numbers, and `check_thresholds`
(`agent/tools/stats.py:293`) only compares values against reporting cutoffs —
it cannot see that a pasted t=7.01 with p=0.48 is arithmetically impossible.
The rubric's `results_validity_dimension` (`quality/rubric.py:89`) is regex
presence-matching over text; it can never catch a wrong value.

This layer closes the hole with **pure, deterministic checks** (no LLM, no
network, no I/O) that verify statistics are *internally consistent and
mathematically possible*, run at both entry points:

1. **The `run_stats` boundary** — validate what the engine just computed.
2. **The parsed/pasted path** — validate what the student uploaded or typed.

It upgrades the core guarantee from **"no invented statistics"** to
**"no incorrect statistics."** Initiatives 6 (coherence gate), 10 (viva), and
12 (certificate) all consume its findings.

## 2. Scope and non-scope

**In scope**

- A pure validation module in `libs/thesis-stats` (new `validation.py`) with a
  claim-based check catalogue (§4) and a typed finding schema (§5).
- A thin dothesis adapter (`agent/stats_validation.py`) that normalizes
  dothesis-specific payload shapes into claims (§6).
- Wiring at: `run_stats` return (§7.1), `check_thresholds` / parsed tables
  (§7.2), the orchestrator step-parse path (§7.3), the M4
  `commit_slice` gate for `analysis_results` (§7.4), and a `stats_validity`
  rubric dimension (§7.5).
- M4 skill guidance for narrating findings (§7.6).

**Out of scope (explicitly deferred)**

- **Cross-chapter coherence (M3 ↔ M4 ↔ M5)** — hypothesis-registry
  reconciliation, prose-vs-state number matching, direction-word agreement.
  That is roadmap initiative #6; this layer only checks numbers against
  *other numbers in the same results payload*, never against prose. The one
  M3-adjacent check kept here (X2, hypothesis coverage) is a soft structural
  count, not semantic reconciliation.
- Power analysis (initiative #2), data screening (#3), new statistical ops of
  any kind. This layer computes **verification arithmetic only** — it never
  produces a new reportable statistic.
- Validation of qualitative results (`qual_codes` / `qual_themes`).
- Re-validation of numbers already rendered into M5 prose (initiative #6's
  reconciliation baseline will reuse these checks).

## 3. Architecture and placement

### 3.1 Decision: pure checks in `thesis-stats`, dothesis-shape adapters in `agent/`

Three options were considered:

| Option | Verdict |
|---|---|
| (a) All logic in a dothesis-only module | Rejected — fillform (the other thesis-stats consumer) computes the same PLS/SPSS payloads and gets zero protection; the checks would also sit away from the engine whose raw output shapes they must track. |
| (b) All logic in `thesis-stats`, including dothesis payload walking | Rejected — the M4 skill's `analysis_results` block shape (`skills/dothesis-m4-analysis/SKILL.md:127-147`) and the parser `StepResult` shape (`orchestrator/schemas/m4.py:11`) are dothesis product schemas; leaking them into the shared engine couples the library to one consumer. |
| **(c) Both — pure checks + engine-native adapters in `thesis-stats`; dothesis-shape adapters in `agent/stats_validation.py`** | **Chosen.** |

Concretely:

- **`libs/thesis-stats/src/thesis_stats/validation.py`** (new) owns:
  - the `Finding` schema and the claim shape (§5, §6.1);
  - every check primitive in the catalogue (§4) — pure functions over claims;
  - `validate_claims(claims) -> list[Finding]` — the composite runner;
  - engine-native adapters `claims_from_pls(raw)`, `claims_from_spss_basic(raw)`,
    `claims_from_spss_regression(raw)`, `claims_from_rigor(raw)` — these
    consume the exact `raw_*` shapes `run_pls`/`run_spss_*`/`run_rigor` return
    (`libs/thesis-stats/src/thesis_stats/smartpls.py:487-502`,
    `spss.py:73`, `spss.py:139`, `rigor.py:237`), so they are unit-tested next
    to the engine and against its golden fixtures
    (`libs/thesis-stats/tests/golden/`);
  - `claims_from_table(table_kind, rows, source="parsed")` — the generic
    parsed-table adapter for `{item|pair|construct, value|values}` rows and
    common column names (`alpha`, `CR`, `AVE`, `beta`, `t`, `p`, `loading`,
    `htmt`). This shape is "a stats table", not a dothesis schema — fillform
    parses the same tables, so it belongs in the shared lib.
  - Convenience: `validate_result(kind, payload, source="computed")` where
    `kind ∈ {"pls","spss_basic","spss_regression","rigor","table"}` — adapter
    dispatch + `validate_claims` in one call (the roadmap's named entry point).
- **`agent/stats_validation.py`** (new, pure — no LangChain, no I/O) owns:
  - `claims_from_run_stats(op, summary)` — maps the *summarized* op payloads
    the tool returns (`agent/tools/stats.py:151-256` — `_summarize_pls`,
    `_op_efa`, `_op_regression_full`, `_op_mediation`, `_op_moderation`,
    `_op_rigor`) to claims. The tool summaries are dothesis shapes, so this
    lives dothesis-side;
  - `claims_from_analysis_results(block)` — walks the persisted
    `analysis_results` structure the M4 skill mandates
    (`measurement_model[]`, `discriminant_validity`, `hypothesis_tests[]`,
    `structural_model`, `descriptives`) plus tolerant fallbacks for the
    orchestrator's `results: {step_name: StepResult}` shape and legacy
    free-text (free text yields zero claims, never a crash);
  - `validate_analysis_results(block) -> list[Finding]` and
    `validate_run_stats(op, summary) -> list[Finding]` — the two composite
    entry points the wiring calls (§7).

Layering is safe in every direction used: `agent/tools/stats.py` already
imports `thesis_stats` lazily (`agent/tools/stats.py:196`), `quality/rubric.py`
already imports `agent.*` lazily (`quality/rubric.py:117`,`:140`), and
`orchestrator/tools/m4_analysis.py` will import `thesis_stats` lazily (the
package is installed editable repo-wide via `requirements.txt:54`).

### 3.2 Why the checks may compute (and `check_thresholds` still may not)

`check_thresholds` deliberately "computes NOTHING" (`agent/tools/stats.py:279-283`)
because it produces *narratable classifications* of pasted numbers, and deriving
new reportable statistics from pasted values would blur the fabrication
boundary. The validator is different in kind: its arithmetic (e.g. recomputing
p from t at the stated df) exists only to **falsify** a claimed number, and its
outputs are findings, never statistics. No validator output is ever a value the
agent may report as a result. This distinction goes in the module docstring and
the M4 skill.

### 3.3 Determinism, purity, dependency constraints

- Every check is a pure function: same claims in → same findings out. No LLM,
  no network, no filesystem, no randomness, no clock.
- Only dependencies already pinned in the engine (`numpy`, `scipy.stats` for
  the t→p survival function). No new packages.
- The validator must be fast enough to run on every `run_stats` return and
  every commit (< a few ms for typical payloads — it is arithmetic over at
  most a few hundred claims).

## 4. Check catalogue

Claims carry `source: "computed" | "parsed"` and optional display precision
(`decimals`); tolerances derive from both (§4.4). "Both" in the *applies*
column means computed and parsed inputs.

### 4.1 Bounds / possibility (category `bounds.*`)

Impossible values. Hard unless noted — a number outside its mathematical range
is a fabrication with extra steps, regardless of where it came from.

| ID | Metric / inputs | Rule | Severity | Applies |
|---|---|---|---|---|
| B1 | R² (`r_squared`, `r2`) | `0 − ε ≤ r² ≤ 1 + ε`. Adjusted R² may be negative; only `> 1 + ε` is a violation for it. | hard | both |
| B2 | AVE | `0 − ε ≤ ave ≤ 1 + ε` | hard | both |
| B3 | Cronbach's α | `α ≤ 1 + ε` (upper bound only — negative α is mathematically possible) | hard | both |
| B3s | Cronbach's α | `α < 0` — possible but almost always reversed/miskeyed items | soft | both |
| B4 | CR / composite ρ | `0 − ε ≤ cr ≤ 1 + ε` | hard | both |
| B5 | Outer loading (PLS family) | `|λ| ≤ 1 + ε` (a PLS loading is an item↔score correlation) | hard | both |
| B5s | Standardized loading, CB-SEM family | `|λ| > 1 + ε` → Heywood case (possible under correlated errors, always a problem) | soft | parsed |
| B6 | Correlation r (incl. Fornell-Larcker off-diagonals) | `|r| ≤ 1 + ε`; a correlation-matrix diagonal, where present, `= 1 ± ε` | hard | both |
| B7 | p-value | `0 ≤ p ≤ 1` (string forms "<0.001" / "&lt;.05" parse to threshold claims, see C3) | hard | both |
| B8 | Variance / SD | `≥ 0 − ε` | hard | both |
| B9 | HTMT | `htmt ≥ 0 − ε` | hard | both |
| B9s | HTMT | `htmt > 1 + ε` — mathematically possible (ratio of correlation means) but signals degenerate discriminant validity or a mis-copied matrix | soft | both |
| B10 | VIF | `vif ≥ 1 − ε` (VIF = 1/(1−R²) ≥ 1; below 1 is impossible) | hard | both |
| B11 | f² | `f² ≥ 0 − ε` (in-sample nested-model definition) | hard computed / soft parsed | both |
| B12 | KMO | `0 ≤ kmo ≤ 1` | hard | both |
| B13 | GoF | `0 ≤ gof ≤ 1` | hard | both |
| B14 | Fit indices | CFI `∈ [0,1]` hard; RMSEA `≥ 0` hard; SRMR `∈ [0,1]` hard; TLI outside `[0,1]` **soft** (TLI is non-normed and can legally exceed 1 or go negative) | mixed | parsed (until initiative #9 computes CB-SEM) |
| B15 | Total variance explained (%) | `0 < pct ≤ 100 + ε` | hard | both |
| B16 | n, df, bootstrap_samples | positive; df ≥ 1; n an integer where claimed | hard | both |

### 4.2 Internal consistency (category `consistency.*`)

Numbers that must agree with each other.

| ID | Inputs | Rule | Severity | Tolerance (computed / parsed) |
|---|---|---|---|---|
| C1 | Construct's full loading set + its AVE | `ave ≈ mean(λᵢ²)`. Runs only when the claim set contains *every* item of the construct (the measurement_model block and `_summarize_pls` both carry full sets; partial pastes skip). | hard | 0.02 / 0.05 |
| C2 | Construct's loading set + CR | Recompute `CR = (Σλ)² / ((Σλ)² + Σ(1−λ²))`; compare. **Soft** even on large gaps: CR formula variants (Dillon-Goldstein ρ, ρ_A, ω) legitimately differ — the engine itself reports `dillon_goldstein_rho` as `cr_rho` (`agent/tools/stats.py:174`). | soft | 0.05 / 0.08 |
| C3 | (t, p) pair, optional df, optional n | Recompute two-tailed `p' = 2·sf(|t|, df)` (df from claim; else `n − k − 1` if derivable; else sweep df ∈ [1, 10⁶]). **Hard** when the reported p is impossible for *every* df in the sweep (e.g. t=7.01 with p=0.48, or t=0.3 with p<0.001). **Soft** when it disagrees with the stated df beyond tolerance but is possible at some df. Threshold claims (`p < .001`) check `p' < threshold`. | hard / soft | p-tolerance: `max(0.005, 0.25·p')` / `max(0.01, 0.5·p')` |
| C4 | Estimate + CI pair | `lo − ε ≤ estimate ≤ hi + ε`, and `lo ≤ hi`. Bootstrap percentile CIs are not forced symmetric — containment only. | hard | ε from decimals (§4.4) |
| C5 | Fornell-Larcker diagonal + AVE | `diag = √ave ± tol` per construct (the F-L diagonal *is* √AVE by construction) | hard | 0.01 / 0.02 |
| C6 | Parser `significant`/`threshold_met` flags + their value | A row claiming `significant: true` with `p ≥ .05 + ε` (or the inverse) contradicts itself (`orchestrator/tools/m4_parsers/smartpls.py:112-117` emits these flags) | hard | ε from decimals |
| C7 | f² + R² of the same endogenous construct | `f² = (R²_incl − R²_excl)/(1 − R²_incl)` implies `R²_excl = R²_incl − f²·(1 − R²_incl)` must lie in `[0, R²_incl]`. Flag when the implied excluded-R² is impossible. | soft | 0.02 / 0.05 |

### 4.3 Cross-table integrity (category `xtable.*`) and suspicious patterns (category `suspect.*`)

| ID | Inputs | Rule | Severity |
|---|---|---|---|
| X1 | All `n` claims in one payload | A single table reporting two different n for the same analysis → **hard**. Different n across *different* tables in one batch → **soft** (listwise deletion per analysis is legitimate, but the student should disclose it). | hard / soft |
| X2 | `hypothesis_tests[]` vs M3 `hypotheses` (passed in as context at the commit gate only) | Every M3 hypothesis id appears in some result entry. Structural count only — semantic reconciliation is initiative #6. | soft |
| X3 | Metric families present in one payload | PLS-family metrics (AVE/HTMT/GoF/f²) and CB-SEM fit indices (CFI/TLI/RMSEA/SRMR) in the same measurement/structural results → violates the standing invariant (`skills/dothesis-m4-analysis/SKILL.md:36-38`, `AGENTS.md`). | hard |
| X4 | Path endpoints vs measurement constructs | A path `A → B` whose construct never appears in the measurement model of the same payload. | soft |
| S1 | All loadings of a payload | every `λ ≥ 0.99` → copied matrix / straight-lined data (extends the existing `check_thresholds` 0.9-heuristic, `agent/tools/stats.py:318-320`) | soft |
| S2 | α or CR | `≥ 0.98` → suspiciously perfect scale | soft |
| S3 | R² | `≥ 0.95` → likely duplicate/derived variable or leakage | soft |
| S4 | All p claims | every reported p identical to 3 decimals across ≥ 4 tests → copy-paste artifact | soft |
| S5 | Loading values | the same value repeated across all items of ≥ 2 constructs → copy-paste artifact | soft |

### 4.4 Tolerances — the rounding policy

False positives on legitimately rounded pasted tables would destroy trust in
the layer, so tolerance is explicit and testable:

- **Display-precision epsilon.** Every claim may carry `decimals` (digits after
  the point as displayed). `ε = 0.5 × 10^(−decimals)` — the half-ulp of the
  displayed value. Defaults when unknown: computed claims `decimals=4` (the
  tool rounds to 4 dp — `agent/tools/stats.py:130-137`, p to 5 dp at `:96`);
  parsed claims `decimals=2` (the most conservative common SmartPLS/SPSS
  display), giving ε = 0.005.
- **Bounds checks** use ε directly: a parsed loading shown as `1.00` (true
  value ≤ 1.004) passes; `1.01` fails.
- **Consistency checks** use `tol = max(check_base_tol, k·ε)` with the per-check
  base tolerances in the §4.2 table and k = number of rounded quantities
  entering the comparison (e.g. C1 sums squared roundings across items).
- **Derived-quantity comparisons** (C3's p′) use relative + absolute floors as
  specified, because sf() is extremely steep in |t| — an absolute-only
  tolerance would misfire near p≈0.
- Every finding records the tolerance it applied (§5), so a disputed finding
  is auditable.

## 5. Finding schema

One schema everywhere — engine, tool boundary, commit gate, rubric:

```json
{
  "check": "consistency.t_p",
  "severity": "hard",
  "message": "Path LS -> PI reports t=7.01 with p=0.48; two-tailed p for t=7.01 is < 0.001 at every df ≥ 1.",
  "location": {"table": "hypothesis_tests", "construct": null, "item": null, "path": "LS -> PI"},
  "observed": {"t": 7.01, "p": 0.48, "df": null},
  "expected": "p consistent with t at the stated df",
  "tolerance": 0.01,
  "source": "parsed"
}
```

- `check` — stable dotted id (`bounds.r2`, `consistency.ave_loadings`,
  `xtable.family_mix`, `suspect.all_loadings_high`, …). Consumers key on it
  (viva question templates in initiative #10, the certificate in #12).
- `severity` — `"hard"` (mathematically impossible or provably
  self-contradictory beyond tolerance) or `"soft"` (possible but suspicious /
  structural gap). Nothing else; no numeric scores.
- `message` — one student-readable sentence with the offending values inline.
- `location` — enough to point at the exact cell; unused keys null.
- `observed` / `expected` / `tolerance` — the audit trail (vision principle 2:
  everything traceable).
- `source` — `"computed"` or `"parsed"`, set by the adapter, so downstream
  surfaces can phrase the fix correctly ("the engine produced" vs "the pasted
  table contains").

Aggregate wrapper used at wiring points:

```json
{"passed": false, "hard": 1, "soft": 2, "findings": [ ... ]}
```

Rubric findings map onto the existing rubric shape (`{issue, fix, chapter,
severity}` — `quality/rubric.py:39-41`) with `issue = message`,
`chapter = "results"`, `severity` passed through, and `fix` templated per
check id.

## 6. Input normalization — the claim shape

### 6.1 Claim

All adapters emit the same flat claim record; all checks consume only claims:

```python
{
  "metric": "loading",            # canonical metric id (see registry below)
  "value": 0.81,                  # or "values": [lo, hi] for CI claims
  "unit": {"construct": "LS", "item": "LS1", "path": None},
  "n": 234, "df": None,           # when stated
  "decimals": 4,                  # display precision when known
  "table": "measurement_model",   # provenance label for location reporting
  "source": "computed",
  "flags": {"significant": True}, # parser-asserted booleans (C6)
}
```

Canonical metric registry (one constant in `thesis_stats.validation`):
`r2, r2_adj, ave, alpha, cr, loading, loading_cbsem, corr, p, t, beta, se,
ci, htmt, fornell_larcker_diag, vif, f2, gof, kmo, bartlett_p, variance,
sd, variance_pct, cfi, tli, rmsea, srmr, chi2_df, n, df, q2`. Adapters map
source-shape column names/keys onto this registry; unknown metrics are
dropped (never guessed), so a novel table degrades to fewer checks, not to
false findings.

### 6.2 Computed inputs

- `claims_from_pls(raw)` walks `raw_outer_model`, `raw_inner_summary`,
  `raw_unidimensionality`, `raw_path_coefficients` + `raw_bootstrap`,
  `raw_htmt`, `raw_fornell_larcker`, `raw_vif`, `raw_f_squared`,
  `raw_goodness_of_fit` (`libs/thesis-stats/src/thesis_stats/smartpls.py:487-502`).
- `claims_from_run_stats(op, summary)` walks the tool's bounded summaries:
  `paths{beta,t,ci95}`, `reliability{r_squared,ave,cronbach_alpha,cr_rho}`,
  `outer_loadings`, `htmt`, `fornell_larcker`, `vif`, `f_squared`,
  `goodness_of_fit` for `pls_sem`/`moderation`
  (`agent/tools/stats.py:151-191`); `kmo`/`bartlett_p`/
  `total_variance_explained` for `efa` (`:203-213`); `regression_result` rows
  (beta/t/p/R²/adj-R²/F, df derivable from n and predictor count —
  `libs/thesis-stats/src/thesis_stats/spss.py:394-467`) for
  `regression_full` and the basic `regression` op (`agent/tools/stats.py:76-98`);
  `effects` for `mediation`; rigor's normality/effect-size/harman blocks
  (`rigor.py:173-237`).

### 6.3 Parsed inputs

- `claims_from_table(table_kind, rows)` accepts the `{table_kind, rows}`
  contract that `parse_smartpls_export` / `parse_output_table` emit
  (`agent/tools/output_parse.py:97`,`:151`; kinds enumerated at `:24-33`) and
  the `check_thresholds` row shape (`agent/tools/stats.py:294-307`):
  `{"item"|"pair": label, "value": v}` rows and matrix rows
  `{"item": label, "values": [...]}`.
- The same adapter accepts the m4-parser `StepResult.table` rows, which carry
  named columns (`loading`, `alpha`, `CR`, `AVE`, `beta`, `t`, `p`, `htmt`,
  plus assertion flags `threshold_met`/`significant` —
  `orchestrator/tools/m4_parsers/smartpls.py:33-38`,`:77-81`,`:110-117`,`:160-166`).
- `decimals` is inferred per value from the parsed string when available;
  otherwise the parsed default (§4.4). Values the parsers set to `None`
  ("unreadable cell", `output_parse.py:54-61`) produce no claim.

### 6.4 Persisted results

`claims_from_analysis_results(block)` walks the M4-skill structured shape
(`skills/dothesis-m4-analysis/SKILL.md:127-147`): `descriptives`,
`measurement_model[]` (full per-construct loading sets → enables C1/C2/C5),
`discriminant_validity.matrix`, `hypothesis_tests[].numbers`
(`beta/t/p/f2` and p-strings like `"<0.001"`), `assumption_checks`,
`structural_model.r2/q2`. It tolerates the orchestrator's
`results: {step: StepResult}` dict (`orchestrator/schemas/m4.py:22-32`) by
delegating each `table` to `claims_from_table`, and yields `[]` for
free-text/legacy shapes.

## 7. Integration points

### 7.1 `run_stats` boundary (computed)

In `agent/tools/stats.py:run_stats`, after `result = fn(file, **(params or {}))`
(`agent/tools/stats.py:361`) and before the JSON return (`:367`):

```python
validation = _validate(op, result)   # lazy import agent.stats_validation; never raises
if validation and validation["findings"]:
    result["validation"] = validation
```

- Findings are **attached, not withheld**: the agent needs the numbers to
  explain the problem to the student ("the bootstrap degenerated — here's
  why"). The deterministic block is at the commit gate (§7.4), which is where
  a wrong number would become product state.
- Payloads stay bounded: the key is present only when findings exist.
- A validator exception is caught, logged (`logger.exception`), and yields no
  `validation` key — fail-open, see §8.

### 7.2 Pasted path — `check_thresholds` and the parse tools

`check_thresholds` (`agent/tools/stats.py:293-321`) keeps its contract and
docstring promise (compare-only classifications) but additionally merges the
validator's findings for the same rows:

```python
findings += _table_findings(table_kind, rows)   # claims_from_table + validate_claims
```

This upgrades the single narration checkpoint the M4 skill already routes
every pasted/parsed table through (`skills/dothesis-m4-analysis/SKILL.md:161-169`
and `:171-185` — export/vision parses feed `check_thresholds` before
narration) without adding a new tool. The parse tools themselves
(`agent/tools/output_parse.py`) stay untouched — they transcribe; validation
happens at the existing choke points (threshold check + commit gate).

### 7.3 Orchestrator step-parse path (B2B / headless pastes)

`run_analysis_step` (`orchestrator/tools/m4_analysis.py:117-143`) attaches
validation to each parsed StepResult before returning:

```python
result = dispatch_parse(data_type, text, step_name)
if result is not None:
    result["validation"] = _validate_step_table(result)  # thesis_stats.claims_from_table, lazy import
```

`StepResult` (`orchestrator/schemas/m4.py:11-19`) gains an optional
`validation: dict | None = None` field so `M4Output.results` carries findings
into the persisted `m4_analysis` column, where the rubric (§7.5) and
`format_step_as_markdown` (`orchestrator/tools/m4_parsers/__init__.py:43`)
can surface them. The orchestrator graph does not go through the agent's
`commit_slice` tool, so for the B2B path the *blocking* semantics live in the
rubric's hard findings (`blocking` list — `quality/rubric.py:282`), which
auto-mode already treats as its gate (vision principle 4's B2B exception).

### 7.4 The commit gate — hard findings block `analysis_results`

**Attach point:** the model-facing `commit_slice` tool wrapper,
`agent/tools/state_tools.py:49-110` — *not* `ProjectStateStore.commit_slice`
(`agent/state.py:251`). Rationale: the store is deliberately module-agnostic
state machinery; the wrapper is already the established place for
deterministic model-facing guards — NON_CONTENT_KEYS stripping
(`state_tools.py:73-82`) and the M3 conceptual-model repair guard
(`state_tools.py:88-97`) both live there, and headless chat reuses the same
tools so both runtimes are covered. `record_decision`
(`agent/headless.py:26-50`) calls the store directly but writes only
`decisions`, never `analysis_results`, so it cannot bypass the gate.

Insert after the M3 guard, before `store.commit_slice` (`state_tools.py:98`):

```python
if module == "M4" and "analysis_results" in writes:
    v = validate_for_commit(writes["analysis_results"], m3_hypotheses)  # never raises
    if v["hard"]:
        return json.dumps({
            "error": "stats_validation_failed — these numbers are mathematically "
                     "impossible or self-contradictory and cannot be committed",
            "findings": v["findings_hard"],
            "hint": "Re-run the analysis, fix the parsed/typed values, or drop the "
                    "impossible entries. Explain the finding to the student in both registers.",
        })
```

- **Hard findings block the commit** by returning an error JSON to the model —
  the same non-raising pattern as `SliceOwnershipError`
  (`state_tools.py:104-107`), so the turn continues and the agent can coach.
- **Soft findings never block**: they ride the success payload as
  `stats_validation_warnings` so the agent must acknowledge them
  ("suspiciously perfect — confirm with the student, then commit again").
- `m3_hypotheses` is read from the already-loaded store slice for X2 only;
  X2 is soft, so an M3 read failure just skips it.

**Reconciling with "advisory, not blocking" (vision principle 4).** The
principle's stated exception is the fabrication boundary, and a hard finding
is by definition a number that cannot be true — "an impossible number is a
fabrication with extra steps" (roadmap #1). So: hard = provably wrong
(bounds, arithmetic contradictions beyond stated tolerance, family mixing —
each check's hard/soft assignment in §4 was made against this bar), and
everything requiring judgment (Heywood cases, HTMT > 1, suspicious
perfection, coverage gaps, CR formula drift) is soft and advisory. The
student is never walled in by a judgment call — only by arithmetic.

**How the student sees it.** The agent narrates the finding (skill §7.6): what
the number claims, why it is impossible (plain register + formal register),
and the concrete fix path (re-run op / re-paste table / correct the typo).
For a parsed source, the agent shows the offending parsed cell and asks for
the correct value — the existing confirm-before-narrate pattern
(`SKILL.md:183-185`). The commit succeeds as soon as the corrected payload
validates.

### 7.5 The rubric dimension — the safety net over persisted state

New `stats_validity_dimension(context_store)` in `quality/rubric.py`, added to
`score_thesis` (`quality/rubric.py:254-287`):

- Reads `m4_analysis.analysis_results` (and the orchestrator `results` dict)
  from the nested store; runs `validate_analysis_results`; maps findings to
  the rubric finding shape with `chapter="results"`.
- Hard findings flow into the existing `blocking` aggregation
  (`quality/rubric.py:282`) — this is what makes the guarantee hold for
  results that entered state *without* passing the chat commit gate
  (orchestrator path §7.3, legacy projects, direct DB writes).
- Score: `1.0` with no findings; each hard finding −0.5, each soft −0.1,
  floored at 0. Weight 0.15. The existing `results_validity_dimension`
  (presence regex, `quality/rubric.py:89-105`) is kept unchanged — presence
  and correctness are different questions.
- Must tolerate every historical `analysis_results` shape (string, dict,
  list) — free text scores 1.0 with a soft "results are unstructured; numbers
  cannot be verified" finding, never a crash (the rubric's never-crash
  global constraint, `quality/rubric.py:183-210` pattern).

### 7.6 Skill and docs surface

- `skills/dothesis-m4-analysis/SKILL.md`: extend the "Output sanity" section
  (`:161-169`): validation now runs automatically at `run_stats` and at
  commit; how to read a `validation` block; the hard-vs-soft contract; the
  two-register narration for a finding; never retype numbers to dodge the
  gate — fix the source.
- `AGENTS.md` invariants table: add the row "hard validation findings block
  `analysis_results` commits — the third hard boundary alongside verified
  sources and whitelisted stats."

## 8. Error handling

- **The validator never raises out of a wiring point.** Every integration
  wraps the call; on exception: log with `logger.exception`, emit the
  analytics event `stats_validation_crashed` (via `agent.analytics.emit`, the
  established no-op-until-wired hook — `quality/rubric.py:54`), and proceed
  as if no findings. Fail-open is deliberate: blocking a student on our own
  bug violates the advisory principle, and the rubric re-check (§7.5) plus
  initiative #12's ledger give later chances to catch what a crashed
  validator missed.
- **Unknown shapes produce zero claims, not errors** (§6.1) — fewer checks,
  never false findings.
- **Non-numeric values** (strings other than recognized p-threshold forms,
  `None`, NaN) produce no claim; NaN/±inf *as a claimed statistic value* is a
  hard `bounds.non_finite` finding (a NaN R² in a results table is an
  impossible reported number).
- The commit gate treats a validator crash as pass-with-warning: the commit
  proceeds and the success payload carries
  `stats_validation: "unavailable"` so the trail records that this commit was
  not verified.

## 9. Testing strategy

Layout follows the existing suites: engine tests in
`libs/thesis-stats/tests/` (run `python -m pytest libs/thesis-stats/tests`),
agent tests in `agent/tests/` (pattern: `agent/tests/test_stats_tool.py`,
`test_state_tools.py`), rubric tests near `tests/test_quality_gate.py`.

1. **Known-good passes (no false positives).**
   - Run `run_pls`/`run_spss_*`/`run_rigor` over the engine's golden fixtures
     (`libs/thesis-stats/tests/golden/`, `tests/capture_golden.py`) →
     `validate_result` returns zero hard findings.
   - The M4 skill's own sample `analysis_results` block
     (`SKILL.md:127-147`) validates clean.
   - Real-shaped parsed tables (reuse `orchestrator/tools/m4_parsers/golden`
     fixtures) validate clean.
2. **Known-bad caught (mutation tests).** For every hard check: take a
   known-good payload, corrupt exactly one value into impossibility
   (R²=1.24, loading=1.31, p=1.7, t=7.01/p=0.48, CI=[0.10,0.30] with β=0.55,
   F-L diagonal ≠ √AVE, AVE inconsistent with its loadings, PLS+CFI mixed,
   negative variance, VIF=0.4), assert exactly the expected `check` id fires
   with `severity: "hard"` and the right `location`.
3. **Rounding tolerance (no false positives at display precision).**
   Parameterized cases: loading `1.00` at 2 dp passes / `1.01` fails; AVE
   printed to 2 dp vs loadings to 3 dp passes C1 within tol; p `0.000`
   as `<0.001` with t=7 passes; β=0.345 with CI `[0.34, 0.35]` at 2 dp
   passes containment.
4. **Severity contract.** Soft-only payloads never produce `hard`; the commit
   gate blocks iff ≥1 hard finding; soft findings appear as warnings on a
   successful commit (test via a temp-dir `ProjectStateStore`, the
   `test_state_tools.py` pattern).
5. **Fail-open.** Monkeypatch the validator to raise → `run_stats` still
   returns numbers; `commit_slice` still commits with
   `stats_validation: "unavailable"`.
6. **Rubric dimension.** `quality/fixtures/good_pls_thesis.json` scores 1.0 on
   `stats_validity`; a corrupted copy produces a hard finding in `blocking`;
   a free-text `analysis_results` yields the soft unstructured finding and no
   crash.
7. **Determinism.** Same payload validated twice → byte-identical findings
   (ordering fixed by claim order).

## 10. Rollout / compatibility notes

- No new tool, no schema migration: `validation` keys are additive on
  existing JSON payloads; `StepResult.validation` is optional-with-default so
  old persisted rows validate under the pydantic schema.
- The gate only fires on *new* M4 commits; existing projects encounter the
  layer through the rubric dimension (advisory surface first).
- thesis-stats version bumps `0.1.0 → 0.2.0` (new public API:
  `validate_result`, `validate_claims`, `claims_from_*`, `Finding`); the
  submodule pointer bump is part of the plan (README workflow:
  `libs/thesis-stats/README.md` "Editing from a consumer").
- Initiative #8/#9 (new ops) must add validation rules for their new tables —
  noted in their roadmap entries already; the claim registry is the extension
  point.
