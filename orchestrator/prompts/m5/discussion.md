# Compose Chapter 5 — Discussion

You are writing Chapter 5 (Discussion) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Research questions: {research_questions}
- Research gaps (M2): {research_gaps}
- Themes / hypotheses results (from Chapter 4): {results} / {qual_themes}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 1200-2000 word Chapter 5 with these sections:
- 5.1 Summary of findings (one paragraph per research question)
- 5.2 Discussion of findings (compare to prior literature; explain consistencies + surprises)
- 5.3 Theoretical contributions (how findings extend / refine the theory used)
- 5.4 Practical implications (managerial / policy recommendations)
- 5.5 Limitations — introduce them in a sentence, then emit `[[DT:limitations]]` on
  its own line: DoThesis fills in the REAL flagged weaknesses (sub-threshold power, a
  not-supported hypothesis, screening removals, borderline validity) from the persisted
  state, framed for disclosure. Discuss each; invent none; hide none.
- 5.6 Suggestions for future research

Cite extensively to back up each interpretation. Write in {language}.

Output: Chapter 5 prose as markdown only.
