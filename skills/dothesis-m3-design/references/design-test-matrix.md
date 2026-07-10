# Design → Test Decision Matrix

Reference for M3. Consult this **before endorsing any analysis method**. State the
rule that applies and cite it. This encodes the single most common novice error —
choosing the wrong statistical test for the design — so the agent stops it early.

DoThesis is quantitative-only (SmartPLS / SPSS). Every path below ends in a
regression- or SEM-family test; there is no qualitative branch.

## The four inputs

Decide the method from four properties of the study, in this order:

1. **Model complexity** — direct effects only, mediation/moderation, or a full
   structural model with latent constructs?
2. **Sample size (n)** — how many usable responses will realistically be collected?
3. **Construct nature** — are latent constructs **reflective** (indicators are
   interchangeable effects of the construct) or **formative** (indicators *cause*
   the construct and are not interchangeable)?
4. **Data / distribution** — multivariate normal or not; prediction-focused vs.
   theory-confirmation goal.

## The decision tree

```
Is there a latent-variable measurement model (multi-item constructs)?
│
├─ NO  (observed/composite variables only)
│   ├─ 1 DV, 2+ IVs, direct effects            → Multiple linear regression (SPSS)
│   ├─ Indirect (X→M→Y) effect of interest      → Regression + PROCESS (Hayes) mediation
│   ├─ IV effect depends on a moderator         → Moderated regression / PROCESS
│   └─ Group-mean comparison (manipulation)     → t-test / ANOVA (SPSS)
│
└─ YES (latent constructs, structural model)
    ├─ Any FORMATIVE construct                  → PLS-SEM (CB-SEM can't cleanly handle formatives)
    ├─ Prediction / theory-building goal        → PLS-SEM
    ├─ Small-to-moderate n (see thresholds)     → PLS-SEM
    └─ All REFLECTIVE, n large, data ~normal,
       goal = theory confirmation / model fit   → CB-SEM (AMOS / Mplus / lavaan)
```

## Method rules and citable thresholds

| Method | Use when | Minimum n (rule) | Key citation |
|---|---|---|---|
| Multiple linear regression | Observed variables, direct effects, 1 DV | ≥ 10–15 per predictor; ≥ 50 + 8·k for the overall test | Green (1991); Cohen et al. (2003) |
| Mediation (PROCESS) | Test an indirect X→M→Y path | As regression, + bootstrap 5,000 samples for the indirect effect | Hayes (2018); Preacher & Hayes (2008) |
| Moderated regression | IV effect conditional on a moderator | As regression, + ~30% for adequate interaction power | Aiken & West (1991) |
| **PLS-SEM** | Formative constructs, prediction focus, complex model, or non-normal data | **Inverse-square-root** / 10× rule: 10× the largest number of arrows pointing at any one construct | Hair et al. (2022), *A Primer on PLS-SEM*; Kock & Hadaya (2018) |
| **CB-SEM** | All-reflective model, theory confirmation, model-fit indices needed, data ~multivariate-normal, larger n | Commonly **n ≥ 150–200**; ≥ 10× free parameters; never below ~100 | Kline (2016); Hair et al. (2019) |

**Hard stops (never approve):**
- CB-SEM below its sample minimum (roughly n < 100–150) → recommend PLS-SEM or a
  simpler regression model instead.
- A reflective/formative **mismatch**: applying a reflective measurement model
  (α, AVE, loadings) to constructs that are theoretically formative, or vice
  versa. Decide reflective vs. formative *before* choosing the estimator.
- CB-SEM with clearly non-normal data and no robust estimator → PLS-SEM.

## Worked justifications

1. **n = 120, formative constructs (e.g. a "marketing-mix" index), prediction of
   purchase intention.** → **PLS-SEM.** Formative constructs rule out CB-SEM's
   reflective assumptions, the goal is predictive, and n is moderate. Cite Hair et
   al. (2022): PLS-SEM handles formative measurement and works at smaller n.

2. **n = 400, five reflective constructs, aim is to confirm an established theory
   and report CFI/RMSEA fit.** → **CB-SEM.** All-reflective, large n, theory
   confirmation with model-fit reporting is exactly CB-SEM's remit (Kline, 2016).
   PLS-SEM would not give the global fit indices the committee expects here.

3. **n = 90, one IV → one DV, a single moderator, observed composite scores.** →
   **Moderated multiple regression** (not SEM). n is too small for either SEM
   family, and with observed composites there is no measurement model to estimate.
   Center predictors and add the interaction term (Aiken & West, 1991).
