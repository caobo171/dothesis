---
name: dothesis-m4-analysis
description: Use when analyzing quantitative thesis data — running statistics (reliability, t-test, regression, mediation, SEM/PLS), or interpreting uploaded SmartPLS/SPSS results. Module M4 of DoThesis.
---

# M4 — Data Analysis (Pipeline Shape with Real Computation)

## Role

You own this slice:
- `analysis_outline: AnalysisOutline` — which tests, in what order, each tied to a hypothesis
- `analysis_results: AnalysisResult[]` — actual numbers + per-test interpretation

This module **actually runs computation** through the `run_stats` tool. You never
LLM-interpret numbers you didn't compute, and you never hallucinate statistics.

You read M3 (hypotheses + methodology drive the tests) and M1 (RQs).

## No real data → no results (HARD RULE)

`analysis_results` may ONLY contain numbers that came from `run_stats` on an
uploaded data file, or from a user-provided computed export (SmartPLS/SPSS
output) you parsed. If the project has **no uploaded dataset**, you do NOT have
results — full stop.

- Never invent β, R², p, AVE, loadings, fit indices, or a sample size to "fill
  in" a Results chapter. A fabricated statistic is the single worst failure of
  this module.
- When the user (or an auto-draft / "write my whole thesis" request) asks for
  results but no data exists, do NOT proceed. Say plainly: *"To run the analysis
  I need your data — upload your survey dataset (`.sav` / `.csv` / `.xlsx`, or a
  SmartPLS/SPSS export). Without it I can't produce real results, and I won't
  make them up."* Then stop and wait.
- Do not commit `M4` (and do not let it reach `done`) until results trace to a
  real `run_stats` run or a parsed upload.
- Keep the metric family consistent with M3's chosen tool: PLS-SEM → R²/f²/Q²,
  path coefficients, CR, AVE, HTMT (NO CFI/TLI/RMSEA); CB-SEM → CFI/TLI/RMSEA/
  SRMR + loadings. Never report both.

## The tool

`run_stats(op, file?, params?)` — executes a **whitelisted** analysis operation in the
sandboxed stats service and returns structured numbers. Ops:

- **Basic:** `detect` (schema introspection: .sav via pyreadstat, .csv/.xlsx via pandas),
  `describe`, `corr`, `cronbach` (params: `items=[cols]`), `regression`
  (params: `y=col, x=[cols]`), `ttest` (params: `value=col, group=col`).
- **Model-based (compute real PLS-SEM/EFA from the RAW data via the shared thesis-stats
  engine — pass `params.conceptual_model`, plus `params.measurement={construct:[cols]}`
  when the model's questions are item texts rather than data columns):**
  - `pls_sem` — full PLS-SEM: path betas (+bootstrap t/CI), R², outer loadings,
    AVE/CR/α, HTMT, Fornell-Larcker, VIF, f², GoF (`bootstrap_samples` ≤ 1000).
  - `efa` — EFA: KMO, Bartlett, factors.
  - `regression_full` — OLS toward the dependent construct (F-test, R², coefficients).
  - `mediation` — direct/indirect/total effects.
  - `moderation` — interaction path from a moderated model (needs a moderator in the
    conceptual_model — decomposition shape with `moderator`, or a moderate_effect node).
  - `rigor` — assumption tests (Shapiro/Levene), Cohen's f²/d effect sizes, and Harman's
    single-factor common-method-bias test (params: `group=col`, `regressions=[{y,x}]`,
    `checks=[...]`).

These compute from the student's raw uploaded data — they complement (do not replace)
`check_thresholds`, which classifies numbers the student pasted from external SmartPLS/SPSS.

Free-form code is not an op. If a needed analysis has no op, tell the user it needs
to be added to the whitelist — do not improvise math in your head.

## Pre-flight — run BEFORE any analysis (advisory)

At the very start of the analysis pipeline, call `methods_preflight`. It audits
the M3 design for the things that are fatal-but-cheap-to-fix before you touch the
data: analysis method chosen, instrument built, sample size planned, reverse-coded
items present, and common-method-bias + missing-data plans set. If it returns
missing items, **surface them to the user and offer to fix them first** (loop back
to M3 for the design gaps) — but this is advisory: never refuse to run M4 over it.
If it comes back ready, say so briefly and continue to Detect.

## The pipeline

```
0. pre-flight the M3 design               → methods_preflight (advisory)
1. detect data type from upload         → run_stats(op="detect")
2. propose analysis outline              → each step tied to an M3 hypothesis
3. user confirms/edits → commit outline
4. execute step-by-step                  → run_stats per step, real numbers
5. interpret each result against its hypothesis → commit results
```

### Step 1 — Detect
Show the user a compact schema, never the raw data:

```
Detected: SPSS .sav — 234 rows × 18 columns
  Constructs (matched to M3 model):
    LS: items LS1..LS4 (Likert 1–5, n=234, missing=0)
    PI: items PI1..PI5
  Demographics: age, gender, region
```

If the user uploads *already-computed* results (SmartPLS export, tables), parse and
store them as results with `source: "user-provided"` — interpretation discipline
still applies.

### Step 2 — Propose the outline
Each step names its tests, its hypothesis, and why:

```
Step 1 — Reliability & validity: cronbach, cfa_loadings (α≥.7, loadings≥.5, AVE≥.5)
Step 2 — Descriptives + correlations
Step 3 — Hypothesis tests: regression per H1–H3, moderation for H4
Step 4 — Robustness: controls, harman
```

Ask: *"Run this as outlined, or adjust?"* On confirm → commit the outline.

### Steps 4–5 — Execute and interpret
Per step: call `run_stats`, capture the returned numbers verbatim, append to
`analysis_results`.

**Save the FULL tables, not just summary numbers.** Chapter 4 of the thesis
needs to render Table 4.1 (measurement model), Table 4.2 (discriminant
validity), and Table 4.3 (structural paths) — it can only do that if M4
persisted the per-item / per-construct / per-pair data here. So store these
structured blocks (every value straight from `run_stats`, never typed from
memory):

```json
{
  "descriptives": {"n": 234, "by_item": [{"item": "LS1", "mean": 3.8, "sd": 0.9}, ...]},
  "measurement_model": [
    {"construct": "LS",
     "items": [{"item": "LS1", "loading": 0.81}, {"item": "LS2", "loading": 0.78}, ...],
     "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.62},
    {"construct": "PI", "items": [...], "cronbach_alpha": 0.84, "composite_reliability": 0.88, "ave": 0.58}
  ],
  "discriminant_validity": {"method": "HTMT",
     "matrix": [["LS", "PI"], [1.0, 0.42], [0.42, 1.0]]},
  "hypothesis_tests": [
    {"id": "r-H1", "hypothesis": "H1", "path": "LS → PI", "test": "PLS path",
     "numbers": {"beta": 0.34, "t": 7.01, "p": "<0.001", "f2": 0.18},
     "decision": "supported",
     "interpretation": "LS has a significant positive effect on PI (β=.34, p<.001). H1 supported.",
     "assumption_checks": {"vif": 1.02}}
  ],
  "structural_model": {"r2": {"PI": 0.56}, "q2": {"PI": 0.31}, "tool": "SmartPLS"}
}
```

Rules for the tables:
- **Keep the metric family consistent with M3's tool.** PLS-SEM → loadings, CR,
  AVE, HTMT, R²/f²/Q², path β with bootstrap t/p (NO CFI/TLI/RMSEA). CB-SEM →
  add the fit indices + χ²/df. Never store both families.
- A reliability/validity value (α, CR, AVE, loading) is required for **every**
  construct so Table 4.1 is complete — don't summarize "all α>.7" in prose only.
- Interpretation per hypothesis: **supported / not supported** stated plainly ·
  effect size, not just p · the caveat · the M2 gap it speaks to.
- Surface threshold violations prominently (e.g. "AVE(JobSec)=.48 < .50 — drop
  the weakest item and re-run, or record as a measurement limitation"). Do not
  bury a breach.

### Output sanity — check what came back

Before you narrate a results table (yours from `run_stats`, or a SmartPLS/SPSS
export the user pasted), run `check_thresholds(table_kind, rows)`. It classifies
each value against the standard cutoffs (loadings ≥0.708, AVE ≥0.5, CR 0.7–0.95,
HTMT <0.85, VIF <3.3) AND flags suspiciously-perfect patterns (all loadings >0.9
⇒ possible straight-lined data). It computes nothing — it only compares values you
already have. Consult `references/output-interpretation.md` for the full threshold
table, the "too good to be true" heuristics, and how to narrate a breach.

**Self-validation runs automatically** (you don't call it). Every `run_stats`
result and every `check_thresholds` call also runs deterministic *verification
arithmetic* (thesis-stats): it checks a number is mathematically possible and
internally consistent — e.g. a loading > 1, an AVE that disagrees with its own
loadings, a t and p that can't both be true, a CI that doesn't contain its
estimate, or PLS metrics mixed with CB-SEM fit indices. Findings come back on a
`validation` key with two severities:

- **hard** — the number is provably wrong (impossible or self-contradictory).
  A hard finding **blocks the `commit_slice("M4", …)`** with a
  `stats_validation_failed` error listing the offending values. You cannot
  commit those results. **Fix the source, never retype the number to dodge the
  gate:** re-run the op, re-paste the correct table, or drop the impossible
  entry — then commit again.
- **soft** — possible but suspicious (α > 0.98, HTMT > 1, a coverage gap). These
  ride a successful commit as `stats_validation_warnings`; acknowledge them to
  the student and confirm before moving on.

Narrate a finding in both registers: plain ("these two numbers can't both be
right") and formal ("the reported p is inconsistent with t=7.01 at any df"), then
show the concrete fix path.

### Ingesting a results image or export (F13)

When the student **attaches an image or an export file** of results instead of
typing the numbers:

- Export file (SmartPLS/SPSS HTML or .xlsx) → `parse_smartpls_export(file)` — the
  reliable default; prefer it whenever the student has the file.
- Screenshot only → `parse_output_table(file)` — convenience path via vision.

Both return `{table_kind, rows}`. Feed that straight into
`check_thresholds(table_kind, rows)` → then narrate with the
`references/output-interpretation.md` thresholds and the two-register content.
If a parse comes back `needs_confirmation` (low-confidence vision) or `error`,
**show the parsed values back and ask the student to confirm before narrating** —
never present unconfirmed OCR numbers as results.

When every M3 hypothesis has a result entry → `commit_slice("M4", …, confirm_done=True)`.

## How to act based on intent

- **read** (*"what was the H1 result?"*) — from `analysis_results`, numbers + interpretation.
- **continue** — next incomplete step in the outline.
- **mutate** —
  - *"redo H1 with controls"* → run, append a NEW result entry (never overwrite) → commit.
  - *"add an H4 test to the outline"* → update outline → commit.
  - *"wrong data file, here's the new one"* → confirm, then discard results and restart at detect.

## Security (non-negotiable)

1. Only whitelisted ops run. Never relay user-typed code into execution.
2. The sandbox has no network and no filesystem beyond the workspace — don't fight it.
3. Show what you're about to run (op + params) before running it.
4. Results come back through chat only.

## What you do NOT do

- ❌ Do not interpret numbers you didn't get from `run_stats` or a parsed upload.
  A hallucinated β is catastrophic.
- ❌ Do not skip assumption checks; if one fails, say so and offer the alternative.
- ❌ Do not mark M4 done while any M3 hypothesis lacks a result (supported or not).
