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

## Building the keep-it argument (marginal numbers)

A value just outside a cutoff is not a verdict. It is a decision the student has to be
able to defend out loud, and the defence is built from **converging evidence plus content
validity** — never from the single breached number alone. Give the student the paragraph,
not the ruling.

**The pattern.** For a marginal indicator, state in order:

1. the value and how far it sits from the convention ("0.49 vs the 0.50 cutoff");
2. what the *other* measurement statistics say for the same construct (α, CR, AVE — if
   those hold, the construct is behaving);
3. what the item means theoretically — does its content clearly belong to this construct;
4. the decision, and the counterfactual ("keeping it; dropping it would not lift AVE
   above the bar and would cost the construct's content coverage").

**Worked cases** (each recurs constantly in practice):

- **Outer loading between 0.40 and 0.708.** Do not drop reflexively. Check whether α and
  AVE for that construct already clear their thresholds; if they do, the item can stay, and
  the justification is that removing it would not materially improve convergent validity
  (Hair et al.). Drop it only when removal actually lifts CR/AVE past the bar.
- **α or CR above 0.90.** Report it as expected, not as a problem, when the construct has
  many items on a homogeneous scale — that is what a short, tightly-worded scale produces.
  Only flag redundancy when the items are near-paraphrases of each other (see the
  "suspiciously perfect" heuristics below), and say which reading you're taking and why.
- **Cross-loading.** The question is the *gap* between the primary and secondary loading
  and whether the item's wording unambiguously belongs to its own construct. An item whose
  content is plainly about willingness-to-pay stays with willingness-to-pay even if it
  loads modestly on a price construct — say that, with the numbers.
- **Fornell–Larcker breach between two theoretically adjacent constructs.** When one
  construct is a direct antecedent of the other, a high correlation is predicted by the
  theory, and √AVE may fall below it without indicating a measurement fault. Report
  HTMT alongside; if HTMT is under the bar, discriminant validity has support from the
  more sensitive criterion, and say so explicitly rather than reporting a bare failure.
- **A non-significant path.** This is a finding, not a defect. Write what it means
  theoretically, why the context may differ from the source study, and what it implies
  for future research. Never treat "the hypothesis wasn't supported" as something to be
  fixed.

**Know when the argument does not exist.** If reliability has already eliminated every
indicator of a construct, stop the pipeline and say so — "at Cronbach's α this construct
lost all of its items; running the structural model on it would be meaningless." An
honest stop is worth more than a chain of computations on a construct that no longer
exists. Same for a construct whose AVE, CR *and* loadings all fail: that is a measurement
problem to disclose, not a paragraph to write around.

## Narration guidance

When you report a table:
1. State the value and the threshold in one sentence ("AVE(JobSec) = 0.48, below
   the 0.50 cutoff").
2. Say what it means for the thesis ("convergent validity for JobSec is not met").
3. Give the fix or the honest limitation ("drop JS3, the 0.51 loading, and re-run;
   or record it as a measurement limitation") — never bury a breach.
