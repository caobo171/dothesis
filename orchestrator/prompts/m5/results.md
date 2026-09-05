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
Write a 3500-6000 word Chapter 4 with these sub-sections (start at 4.1 — the
chapter title is added automatically, do not repeat it).

A results chapter is the most table-dense chapter of the thesis, and each table
carries its own interpretation. One sub-section per diagnostic — not a single
paragraph that lists every statistic in a row. A chapter that narrates the
numbers in prose instead of tabulating them has failed this brief, however
fluent the prose is.
**Statistics tables are inserted for you — DO NOT write them yourself.** Where a
table belongs, emit the matching token on its OWN line and nothing else; DoThesis
replaces it with the exact table rendered from the persisted results (every number
verbatim). Never hand-type a β/t/p/loading/AVE/fit table — a table you type can
carry a transposed digit; a token cannot. Write only the overview sentence before
each token and the interpretation paragraph after it.

Available tokens: `[[DT:descriptives]]`, `[[DT:measurement_model]]`,
`[[DT:scale_reliability]]`, `[[DT:discriminant_validity]]`, `[[DT:model_fit]]`
(CB-SEM), `[[DT:structural_paths]]`, `[[DT:r2_q2]]`.

Emit EVERY token whose statistic the results carry. A diagnostic that was
computed and then left out of the chapter reads as a diagnostic that was never
run. Skip a token only when the underlying numbers genuinely do not exist.

- 4.1 Chapter introduction — what this chapter reports, in the order it reports
  it, and the sample it rests on. No tables.
- 4.2 Sample characteristics — overview sentence, then `[[DT:descriptives]]`,
  then a paragraph reading the profile: who these respondents are and what that
  means for how far the findings travel.
- 4.3 Assessment of the measurement model. One sub-section per diagnostic, each
  with its own overview sentence, token, and interpretation paragraph:
  - 4.3.1 Indicator reliability — `[[DT:measurement_model]]`. Report the loading
    range, name the weakest indicators, and say whether each clears 0.70.
  - 4.3.2 Internal consistency reliability — `[[DT:scale_reliability]]`
    (Cronbach's α, rho_A, CR per construct, each against its 0.70 threshold).
  - 4.3.3 Convergent validity — read AVE per construct against 0.50.
  - 4.3.4 Discriminant validity — `[[DT:discriminant_validity]]`, stating the
    criterion applied (HTMT < 0.85/0.90, or Fornell-Larcker) and the largest
    value observed.
  - If any **AVE < 0.50** or **loading < 0.50** or **α/CR < 0.70**: state the
    breach explicitly, say which item is affected, and give the correct
    remediation — either the item was dropped and the model re-estimated, OR
    flag it as a measurement limitation to be carried into the Discussion and
    Conclusion (Chapter 5). Do NOT excuse a low AVE with "CR is high" and move on.
- 4.4 Assessment of the structural model:
  - 4.4.1 Collinearity — report the VIF values and the 3.3/5.0 threshold used.
  - 4.4.2 Explanatory and predictive power — `[[DT:r2_q2]]`, reading R² per
    endogenous construct as substantial/moderate/weak, and Q² > 0 where present.
  - 4.4.3 Effect sizes — f² per path against 0.02/0.15/0.35, where available.
  - 4.4.4 Model fit — `[[DT:model_fit]]` for CB-SEM (SRMR/CFI/TLI/RMSEA), or
    SRMR/NFI for PLS-SEM where reported.
- 4.5 Hypothesis testing:
  - 4.5.1 Direct effects — overview sentence, then `[[DT:structural_paths]]`,
    then one short paragraph PER hypothesis: the coefficient, its t/p, and the
    supported/not-supported verdict in the study's own words.
  - 4.5.2 Indirect and mediating effects — where the model has a mediator, report
    the specific indirect effect and classify the mediation (full/partial/none).
- 4.6 Summary of hypothesis testing — a consolidated pass over every hypothesis,
  reproducing the coefficients unchanged from the tables above.
- 4.7 Chapter summary — what the model established, handing the reader into the
  discussion. No new numbers.

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
