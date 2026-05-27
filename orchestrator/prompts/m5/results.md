# Compose Chapter 4 — Results

You are writing Chapter 4 (Results) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Mixed design type (mixed only): {mixed_design_type}
- Data type detected (M4): {data_type_detected}
- Per-step results (quant, from M4): {results}
- Qualitative codes (from M4): {qual_codes}
- Qualitative themes (from M4): {qual_themes}
- Custom ad-hoc analyses: {custom_analyses}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions

### If paradigm == "quantitative"
Write a 1200-2000 word Chapter 4 with these sections:
- 4.1 Sample characteristics (descriptives from results)
- 4.2 Measurement model evaluation (reliability + validity from results)
- 4.3 Hypothesis testing / structural model (path coefficients, regression coefficients, fit indices from results)
- 4.4 Summary of supported / rejected hypotheses

For each result table reference, integrate the numbers from {results} naturally into prose. Flag any threshold breaches (`⚠️` markers from M4 mean the threshold was missed).

### If paradigm == "qualitative"
Write a 1200-2500 word Chapter 4 using the Braun & Clarke (2006) thematic-analysis writeup pattern:
- 4.1 Sample characteristics + context
- 4.2 to 4.N (one section per theme in {qual_themes})
  - Theme name as section heading
  - Synthesize codes belonging to this theme from {qual_codes}
  - Embed 1-2 verbatim quotes per theme (drawn from qual_codes[*].quote)
  - Link back to literature where appropriate
- 4.{N+1} Integration of themes (how themes relate to each other and to the research questions)

### If paradigm == "mixed"
Use {mixed_design_type} to structure:
- 4.1 Sample characteristics (both phases)
- 4.2 Quantitative results (as in the quant section above)
- 4.3 Qualitative results (as in the qual section above)
- 4.4 Integration: convergence, divergence, expansion (explain how quant + qual results inform each other)

Cite inline as (Author, Year). Write in {language}.

Output: Chapter 4 prose as markdown only.
