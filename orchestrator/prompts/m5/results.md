# Compose Chapter 4 — Results

You are writing Chapter 4 (Results) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Mixed design type (mixed only): {mixed_design_type}
- Analysis tool (from M3): {tool}
- Data type detected (M4): {data_type_detected}
- Per-step results (quant, from M4): {results}
- Qualitative codes (from M4): {qual_codes}
- Qualitative themes (from M4): {qual_themes}
- Custom ad-hoc analyses: {custom_analyses}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## NON-NEGOTIABLE — do not fabricate data
- Report ONLY numbers that appear in `{results}` (or `{qual_codes}`/`{qual_themes}`).
  Copy them verbatim. NEVER invent or "fill in" a sample size, β, R², p-value,
  loading, AVE, reliability, or fit index.
- If `{results}` is empty or missing the numbers a section needs, DO NOT make
  them up. Write one short sentence that the empirical analysis for that part is
  pending data collection, and move on. A thin honest Results chapter is
  acceptable; a fabricated one is not.
- Do NOT present illustrative/simulated figures as if they were collected. Every
  reported statistic must trace to `{results}`.

## Method consistency — report ONLY metrics that match `{tool}`
Different analysis methods produce different statistics. Report the family that
matches `{tool}`; never mix them.
- **PLS-SEM** (SmartPLS, PLS, variance-based): report path coefficients (β) with
  bootstrap t-values / p-values, R², adjusted R², f², Q² (predictive relevance),
  composite reliability (CR), AVE, and discriminant validity via HTMT or
  Fornell-Larcker. **Do NOT report CFI, TLI, RMSEA, χ²/df, SRMR** — these are
  covariance-based (CB-SEM) fit indices that SmartPLS does not produce.
- **CB-SEM** (AMOS, Mplus, lavaan): report model fit (χ²/df, CFI, TLI, RMSEA,
  SRMR), standardized loadings, CR, AVE, and standardized path estimates.
- **Regression / SPSS**: report β (standardized + unstandardized), t, p, R²,
  adjusted R², F, and VIF for multicollinearity.
- If `{tool}` is unclear, infer the family from what `{results}` actually
  contains and stay internally consistent — never report two incompatible
  families in the same chapter.

## Instructions

### If paradigm == "quantitative"
Write a 1200-2000 word Chapter 4 with these sub-sections (start at 4.1 — the
chapter title is added automatically, do not repeat it):
**Statistics tables are inserted for you — DO NOT write them yourself.** Where a
table belongs, emit the matching token on its OWN line and nothing else; DoThesis
replaces it with the exact table rendered from the persisted results (every number
verbatim). Never hand-type a β/t/p/loading/AVE/fit table — a table you type can
carry a transposed digit; a token cannot. Write only the overview sentence before
each token and the interpretation paragraph after it.

Available tokens: `[[DT:descriptives]]`, `[[DT:measurement_model]]`,
`[[DT:discriminant_validity]]`, `[[DT:model_fit]]` (CB-SEM), `[[DT:structural_paths]]`,
`[[DT:r2_q2]]`.

- 4.1 Sample characteristics — overview sentence, then `[[DT:descriptives]]`.
- 4.2 Measurement model evaluation (reliability + validity).
  - Overview sentence, then `[[DT:measurement_model]]` (Table 4.1).
  - If any **AVE < 0.50** or **loading < 0.50** or **α/CR < 0.70**: state the
    breach explicitly, say which item is affected, and give the correct
    remediation — either the item was dropped and the model re-estimated, OR
    flag it as a measurement limitation to be carried into the Discussion and
    Conclusion (Chapter 5). Do NOT excuse a low AVE with "CR is high" and move on.
  - Then `[[DT:discriminant_validity]]` (Table 4.2, HTMT or Fornell-Larcker).
- 4.3 Hypothesis testing / structural model.
  - Overview sentence, then `[[DT:structural_paths]]` (Table 4.3), and
    `[[DT:model_fit]]` for CB-SEM · `[[DT:r2_q2]]` for the explanatory/predictive power.
  - Interpret the structural metrics for the `{tool}` family (R²/f²/Q² for PLS-SEM;
    fit indices for CB-SEM) — effect sizes, not just significance.
- 4.4 Summary of supported / rejected hypotheses.

### If paradigm == "qualitative"
Write a 1200-2500 word Chapter 4 using the Braun & Clarke (2006) thematic-analysis
writeup pattern (start at 4.1):
- 4.1 Sample characteristics + context
- 4.2 to 4.N (one section per theme in `{qual_themes}`)
  - Theme name as section heading
  - Synthesize codes belonging to this theme from `{qual_codes}`
  - Embed 1-2 VERBATIM quotes per theme (drawn from `qual_codes[*].quote`) with a
    participant id + role/field note — never invent quotes.
  - Link back to literature where appropriate
- 4.{N+1} Integration of themes (how themes relate to each other and to the RQs)

### If paradigm == "mixed"
Use `{mixed_design_type}` to structure (start at 4.1):
- 4.1 Sample characteristics (both phases)
- 4.2 Quantitative results (as in the quant section above — tables + tool-
  consistent metrics)
- 4.3 Qualitative results (as in the qual section above — verbatim quotes)
- 4.4 Integration: convergence, divergence, expansion (explain how quant + qual
  results inform each other; cross-reference specific numbers and quotes)

## Interpretation patterns (every table needs interpreting prose)

Each results table follows the same shape: **[overview sentence] → [table] →
[detailed interpretation of the key values] → [closing comment]**. Never leave a
table standing alone. Adapt these model sentences (fill the brackets from `{results}`):

- Sample/descriptives: *"The study obtained [n] valid responses out of [total]
  distributed (a response rate of [%])."* Then interpret each demographic.
- Reliability: *"The reliability test in Table 4.1 shows all constructs have
  Cronbach's α above 0.70, meeting the threshold."* If an item was dropped:
  *"Item [X] was removed because its corrected item-total correlation fell below 0.30."*
- EFA: *"The EFA returned KMO = [value] (> 0.5), a significant Bartlett's test
  (Sig = 0.000), and total variance explained of [%] (> 50%)."*
- Correlation: *"All independent variables correlate with the dependent variable
  at the 1% significance level (Sig < 0.01)."*
- Regression / structural: *"The model explains [%] of the variance in the
  dependent variable (adjusted R² = [value])."*
- Hypothesis test: *"H1 is supported, with β = [value] and Sig = [value]."* Then
  rank the supported paths by effect size, not just significance.

Cite inline as (Author, Year); for narrative citations where the author is the
sentence subject, use "Author (Year)". Write in {language}.

Output: Chapter 4 prose as markdown only.
