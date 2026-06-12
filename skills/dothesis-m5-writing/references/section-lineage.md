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
| Discussion | sources being compared | gaps being filled | all (verbatim restatement) | the result per hypothesis |
| Conclusion | — | locked gaps | all | headline numbers |
| References | every id in any other section's lineage.sources | — | — | — |

Use the lineage to answer two recurring needs:

1. **needs_review resolution** — when M4 changes, sections whose `lineage.results`
   include the changed entries are the ones to rewrite; everything else stands.
2. **Reference completeness** — the References section is *derived*: the union of all
   `lineage.sources`. A source cited in prose but missing from the union means a
   lineage bug — fix the section entry, don't hand-edit references.
