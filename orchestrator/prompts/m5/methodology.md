# Compose Chapter 3 — Methodology

You are writing Chapter 3 (Methodology) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Research design: {design}
- Analysis tool: {tool}
- Conceptual model (quant): {conceptual_model}
- Themes (qual): {themes}
- Scale items (quant): {scale_items}
- Interview guide (qual): {interview_guide}
- Sampling strategy: {sampling_strategy}
- Target sample size: {target_sample_size}
- Purposive criteria (qual): {purposive_criteria}
- Mixed design type (mixed only): {mixed_design_type}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Ground rules
- Use only the values in the Inputs. The sample size is `{target_sample_size}` —
  do NOT invent a different figure, and do NOT claim data has already been
  collected/analysed (that is Chapter 4's job; here you describe the planned
  procedure). Never narrate missing inputs or assumptions you made to fill gaps.
- The analysis tool you justify in 3.5 MUST be `{tool}`, and it MUST be the same
  method family that Chapter 4 reports. If `{tool}` is PLS-SEM (SmartPLS), the
  results will be variance-based (R²/f²/Q², path coefficients) — do not describe
  a covariance-based (CB-SEM) procedure with CFI/TLI/RMSEA, and vice-versa.

## Instructions
For paradigm = quantitative, write sections:
- 3.1 Research design rationale (justify quant approach + chosen design)
- 3.2 Population and sampling (sampling_strategy + target_sample_size)
- 3.3 Instrument: measurement model + scale items per construct. When
  `{scale_items}` is provided, you MUST render the full item list as a Markdown
  table with columns **Thang đo (construct) | Mã hóa | Biến quan sát (item)**
  (Vietnamese) or **Construct | Code | Item** (English), one row per item, using
  the exact item wording given — never summarise or invent items. Put a bold
  caption `**Bảng 3.1: Thang đo các khái niệm nghiên cứu**` on its own line
  immediately before the table, then interpret it briefly in prose after.
- 3.4 Data collection procedure
- 3.5 Data analysis approach (justify tool `{tool}` — and stay consistent with
  the metric family Chapter 4 will report)

For paradigm = qualitative, write sections:
- 3.1 Research approach + Braun & Clarke (2006) justification
- 3.2 Purposive sampling rationale + criteria
- 3.3 Interview guide structure with example probes
- 3.4 Data collection logistics
- 3.5 Thematic analysis 6-step procedure (familiarization → coding → themes → review → naming → writing)

For paradigm = mixed, include both above + 3.6 integration section explaining the {mixed_design_type} sequencing.

## Model sentences (quantitative sections)

Adapt these standard academic phrasings — fill the brackets from the Inputs, never invent figures:

- 3.1 Process: *"The research was conducted through a [N]-step process: (1)..., (2)..., (3)..."*
- 3.2 Data collection: *"Primary data were collected through a structured
  questionnaire survey, distributed online via Google Forms from [month] to [month] [year]."*
- 3.3 Instrument: *"The questionnaire comprised two parts: Part 1 captured
  demographic information ([k] items), and Part 2 measured the research constructs
  ([m] items) on a five-point Likert scale."* State the source reference for each scale.
- 3.4 Sampling: *"Following Hair et al. (2014), the minimum sample for EFA is n ≥ 5
  × the number of observed items; with [m] items the minimum is [5m]. The study
  targets [target_sample_size] valid responses."*
- 3.5 Analysis: *"Data were analysed using [tool] through: (1) descriptive
  statistics, (2) reliability testing (Cronbach's α), (3) EFA, (4) Pearson
  correlation, (5) [the structural/regression step matching {tool}]."*

Keep the analysis steps consistent with the metric family Chapter 4 reports
(variance-based for PLS-SEM; covariance-based fit indices for CB-SEM).

Cite inline as (Author, Year). Write in {language}. Length: 800-1500 words.

When you describe the data-screening/cleaning procedure, introduce it in a sentence,
then emit `[[DT:data_cleaning]]` on its own line — DoThesis inserts the committee-ready
cleaning paragraph + summary rendered verbatim from the screening results (every count
computed). Do not hand-type the removal counts.

Output: Chapter 3 prose as markdown only.
