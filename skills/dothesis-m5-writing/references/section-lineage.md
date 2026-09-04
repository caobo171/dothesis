# Section lineage — which state feeds which chapter

Every `DocumentSection` records its lineage so revisions know what to re-check when
upstream state changes:

```ts
{
  id: "s3",
  title: "Literature Review",
  body: "<prose>",
  lineage: {
    sources: ["src-001", "src-002"],   // literature_sources ids used
    gaps: ["gap-1", "gap-2"],          // research_gaps ids argued
    hypotheses: [],                     // hypothesis labels referenced
    results: []                         // analysis_results ids reported
  }
}
```

| Section | lineage.sources | lineage.gaps | lineage.hypotheses | lineage.results |
|---|---|---|---|---|
| Abstract | summary only | locked gaps | all | headline numbers |
| Introduction | 2–4 framing sources | locked gaps (brief) | — | — |
| Literature Review | all cited | all locked | — | — |
| Theoretical Framework | scale/theory sources | grounding gaps | all | — |
| Methodology | instrument-source scales | — | — | — |
| Results | — | — | all (one block each) | all |
| Conclusions and Recommendations (Chapter 5) | sources being compared | gaps being filled + locked gaps | all (verbatim restatement) | the result per hypothesis, plus the headline numbers |
| References | every id in any other section's lineage.sources | — | — | — |

Chapter 5 is ONE section, not two. A Vietnamese quantitative thesis ends at
**Chương 5 — Kết luận và Kiến nghị** and writes the discussion of findings
inside it (5.1 summary, 5.2 discussion, 5.3 implications, …), which is why
`conclusion` is the only closing chapter key in `M5_CHAPTER_ORDER`. Its lineage
is therefore the union of what the old Discussion and Conclusion sections each
carried: it compares results against the sources, answers the locked gaps, and
restates every hypothesis with its result. A student asking to "write the
discussion" means this material — never a sixth chapter.

Use the lineage to answer two recurring needs:

1. **needs_review resolution** — when M4 changes, sections whose `lineage.results`
   include the changed entries are the ones to rewrite; everything else stands.
2. **Reference completeness** — the References section is *derived*: the union of all
   `lineage.sources`. A source cited in prose but missing from the union means a
   lineage bug — fix the section entry, don't hand-edit references.
