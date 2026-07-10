# Output interpretation — thresholds & sanity checks

Reference for M4: how to read a results table the student pasted (SmartPLS / SPSS
output), which numbers pass, which fail, and which "pass" so cleanly they're
probably bad data. Pair this with the `check_thresholds` tool — the tool does the
mechanical comparison; this file is the *why* and the narration guidance.

**Never derive these numbers yourself.** `check_thresholds` (and you) only
CLASSIFY values that came from `run_stats` or a parsed upload. A threshold is a
comparison, not a computation.

## Threshold table

### Measurement model (reflective, PLS-SEM)

| Statistic | Rule | Reading |
|---|---|---|
| Outer loading | ≥ 0.708 | Below → item explains <50% of construct variance; consider dropping (0.4–0.708: drop only if it lifts CR/AVE above the bar). |
| Indicator reliability (loading²) | ≥ 0.50 | Restates the 0.708 loading rule. |
| Cronbach's α | 0.70–0.95 | <0.70 weak reliability; >0.95 redundant items (near-duplicates). |
| Composite reliability (CR / ρc) | 0.70–0.95 | Same band as α; >0.95 is a red flag, not a prize. |
| AVE | ≥ 0.50 | Convergent validity — construct explains ≥50% of its indicators' variance. |

### Discriminant validity

| Statistic | Rule | Reading |
|---|---|---|
| HTMT | < 0.85 (strict) / < 0.90 (lenient) | ≥ threshold → two constructs may be the same thing; discriminant validity fails. |
| Fornell–Larcker | √AVE > inter-construct r | Each construct shares more variance with its own items than with others. |

### Structural model

| Statistic | Rule | Reading |
|---|---|---|
| Collinearity VIF | < 3.3 (ideal) / < 5 (tolerable) | ≥ 5 → predictors overlap; path estimates unstable. |
| Path coefficient p-value | p < 0.05 | With bootstrap t ≥ 1.96 (two-tailed). Report β **and** the effect, not just "significant". |
| R² | 0.25 / 0.50 / 0.75 = weak / moderate / substantial | Context-dependent — consumer behaviour R²≈0.30 is normal. |
| f² | 0.02 / 0.15 / 0.35 = small / medium / large | Effect size of one predictor. |
| Q² | > 0 | Predictive relevance (blindfolding / PLSpredict). |

### CB-SEM model fit (AMOS / Mplus / lavaan)

| Statistic | Rule |
|---|---|
| CFI / TLI | ≥ 0.90 (acceptable) / ≥ 0.95 (good) |
| RMSEA | ≤ 0.08 (acceptable) / ≤ 0.06 (good) |
| SRMR | ≤ 0.08 |
| χ²/df | < 3 |

> Keep the metric family consistent with M3's tool. PLS-SEM reports loadings/CR/
> AVE/HTMT/R²/f²/Q² — **never** CFI/TLI/RMSEA. CB-SEM adds the fit indices. Never
> report both families for one model.

## "Suspiciously perfect" heuristics — flag, don't celebrate

Numbers that look *too* good usually mean a data or import problem, not a great
study. Surface these as a caution:

- **All outer loadings > 0.90** across a construct → likely straight-lined
  responses (a respondent picking the same column) or a wrong/duplicated matrix.
- **CR or α > 0.95** → redundant items measuring the same nuance twice.
- **Every hypothesis supported at p < 0.001** with large β → check for a common-
  method-bias inflation (run Harman / a marker variable) before believing it.
- **HTMT ≈ 1.0** → the two constructs are empirically identical; merge or redesign.
- **Zero missing data on a long online survey** → check the export, not luck.

## Narration guidance

When you report a table:
1. State the value and the threshold in one sentence ("AVE(JobSec) = 0.48, below
   the 0.50 cutoff").
2. Say what it means for the thesis ("convergent validity for JobSec is not met").
3. Give the fix or the honest limitation ("drop JS3, the 0.51 loading, and re-run;
   or record it as a measurement limitation") — never bury a breach.
