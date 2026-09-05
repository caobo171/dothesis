# Compose Chapter 5 — Conclusions and Recommendations

You are writing Chapter 5, the FINAL chapter of a master's thesis.

A Vietnamese quantitative thesis has five chapters. The discussion of findings
belongs INSIDE this chapter (5.2), not in a chapter of its own — do not write a
separate discussion chapter and do not refer to a chapter after this one; this
is the last chapter of the thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Objectives: {objectives}
- Research questions: {research_questions}
- Research gaps (M2): {research_gaps}
- Themes / hypotheses results (from Chapter 4): {results} / {qual_themes}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 2500-4000 word Chapter 5 with these sections. Each section carries its
own argument at length — a closing chapter that reduces every section to a
paragraph reads as a summary of the thesis rather than its conclusion.
**No statistics tables in this chapter.** Every results table — loadings,
α/CR/AVE, HTMT, path coefficients, R²/f² — belongs to Chapter 4 and is rendered
there. Chapter 5 reads what those numbers MEAN; it never reprints them as a
table, and it does not restate the measurement-model diagnostics at all. Refer
to a finding in words ("the effect of X on Y was the strongest path"), citing
Chapter 4's table by number where it helps. A table here is a duplicate of
Chapter 4 and will be read as padding.

- 5.1 Summary of findings (one paragraph per research question; state how each
  objective was met — in prose, no tables)
- 5.2 Discussion of findings (compare to prior literature; explain consistencies
  + surprises)
- 5.3 Theoretical contributions (how findings extend / refine the theory used)
- 5.4 Practical implications and recommendations (managerial / policy)
- 5.5 Limitations — introduce them in a sentence, then emit `[[DT:limitations]]` on
  its own line: DoThesis fills in the REAL flagged weaknesses (sub-threshold power, a
  not-supported hypothesis, screening removals, borderline validity) from the persisted
  state, framed for disclosure. Discuss each; invent none; hide none.
- 5.6 Directions for future research
- 5.7 Concluding remarks (concise; no new claims, no new citations)

Cite extensively in 5.2 and 5.3 to back up each interpretation. Write in {language}.

Output: Chapter 5 prose as markdown only.
