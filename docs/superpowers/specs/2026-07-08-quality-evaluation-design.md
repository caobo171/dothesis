# Quality Evaluation of Output Design

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Sequence:** Spec 3 of the follow-on set (quality-evals → cross-session memory →
observability). Consumes read contracts owned by later specs (`institution_profile`,
`advisor_feedback`) with safe empty defaults, so it ships standalone and gets richer as they
land.

## Problem

DoThesis has no measure of whether a generated/edited thesis is any good: no rubric grading,
no "would this pass a committee" check, no regression gate when prompts/models change. A
student can't tell if their Results chapter is defensible; the team can't tell if a model
swap (Gemini ↔ Claude) degraded output.

## Goals

- **One scorer, two callers:** a student-facing readiness grader AND an internal CI harness
  reuse the *same* rubric, so "what good looks like" is defined once.
- **Layered, method-aware rubric:** base criteria adapt to the student's quant method
  (PLS-SEM / CB-SEM / SPSS); an `institution_profile` overlays weights + hard requirements.
- **Advisor feedback is a hard rubric input:** open professor directives (`advisor_feedback`)
  become required criteria — the rubric fails a chapter that ignores them.
- **Actionable output:** every dimension returns a score PLUS specific fixes (issue + fix +
  chapter), not just a number.
- **Advisory, not blocking:** the truly dangerous cases (fabricated citations, empty
  results) are already hard-gated elsewhere; this warns and guides.

## Non-goals

- Not a stats engine (students run their own software; `project_agent_gaps` memory).
- Does NOT own `institution_profile` or `advisor_feedback` ingestion/persistence — that's the
  cross-session-memory spec. This spec only *reads* them (empty default).
- Not a hard export gate. Existing gates (`validate_citations`, M4 data gate) stay the hard
  stops; this is a coaching signal.

## Design

### Layered rubric

```python
RubricResult = {
  "overall": float,           # 0..1 weighted
  "method": str,              # "pls-sem" | "cb-sem" | "spss" | "generic"
  "dimensions": [ {
     "name": str, "score": float, "weight": float,
     "findings": [ {"issue": str, "fix": str, "chapter": str, "severity": "hard"|"soft"} ] } ],
  "advisor": {"total": int, "addressed": int, "open": [ {directive} ]},
  "blocking": [str],          # hard failures (reuses assess_export_readiness / citation gate)
}
```

**Dimensions:**

| Dimension | Kind | Reuses |
|---|---|---|
| Structural completeness | deterministic | `assess_export_readiness(store, chapters)` (Spec 1) |
| Citation integrity | deterministic | `validate_citations` (`orchestrator/tools/m5_writing.py:158`) + `_is_stub_prose` (`:1090`) |
| Methodological soundness | LLM-judge | hypotheses↔gaps trace, method↔design fit |
| Results validity | mixed | method-aware threshold presence (deterministic) + "results address each hypothesis" (judge) |
| Writing quality | LLM-judge | coherence, academic tone, no placeholder stubs |
| **Advisor directives** | deterministic + judge | `advisor_feedback` open items (see below) |

**Method-awareness:** `method` is derived from `m3_design.methodology`. It selects the
Results/Methodology criteria set (e.g. PLS-SEM ⇒ check AVE/CR/HTMT/path-significance/R²/f²
are reported + interpreted; SPSS ⇒ regression assumptions + effect sizes). One rubric, a
method-keyed criteria table.

**Institution overlay:** `institution_profile` (read; default generic) overrides dimension
weights and adds hard requirements: `{citation_style, min_references, reporting_standard,
required_sections, weight_overrides}`. Applied on top of the method base.

### Advisor feedback as rubric input

`advisor_feedback` (owned by the cross-session-memory spec; read here, default `[]`) is a
list of directives `{id, chapter, section?, issue, required_change, status}`. The rubric:
- Counts `total`/`addressed`/`open`.
- Each **open** directive becomes a **hard finding** on its chapter ("advisor required: X —
  not yet addressed"), pulling that dimension's score down.
- The student-facing grader surfaces open directives prominently; the coaching layer can
  turn each into a roadmap blocker via `flag_blocker` (Spec 2).

### The scorer module

`quality/rubric.py`:
- `score_thesis(context_store, *, institution_profile=None, advisor_feedback=None) -> RubricResult`
  — pure orchestration over the deterministic checks + a bounded set of LLM-judge calls.
- Judge calls use the engine LLM (`_get_llm`), each returning strict JSON `{score, findings}`;
  best-effort (a judge failure degrades that dimension to a neutral score + a "could not
  evaluate" note, never crashes the whole score).

### Two callers

- **Student-facing:** `review_thesis()` agent tool + an M5 roadmap `review` sub-step (Spec 2
  spine gains `review` before `export`). Renders `RubricResult` as a score card + fixes in
  chat. Advisory.
- **CI harness:** `quality/eval_harness.py` runs `score_thesis` over a fixture set of
  `context_store` JSON files under `quality/fixtures/`, prints a table, and exits non-zero if
  any fixture's `overall` drops below its recorded baseline (regression gate for prompt/model
  changes).

## Data flow

```
student: "grade my draft" / M5 review step
   → review_thesis tool → score_thesis(store, profile, feedback)
        deterministic checks (structure, citations, stubs, thresholds)
        + method-keyed judge calls
        + advisor open-directive check
   → RubricResult → score card + fixes in chat  (advisory)
CI: pytest quality/eval_harness.py → score_thesis over fixtures → regression gate
```

## Error handling

- Every judge call is best-effort: JSON-parse failure or timeout ⇒ neutral dimension score +
  a "could not evaluate" finding; the overall score still returns.
- Missing `institution_profile`/`advisor_feedback` ⇒ generic defaults / empty; never a crash.
- `score_thesis` is read-only — no writes to project state, so it can't corrupt a thesis.

## Testing

- **Deterministic dimensions:** fixtures where structure/citations/stubs are known-bad ⇒
  assert the finding + severity; known-good ⇒ no finding.
- **Method selection:** `m3_design.methodology` = PLS vs SPSS ⇒ assert the right Results
  criteria set is applied.
- **Advisor directives:** an open directive on chapter 4 ⇒ hard finding on results; marking it
  addressed ⇒ finding clears.
- **Institution overlay:** a profile with `min_references: 30` ⇒ a 12-ref thesis fails that
  requirement; default profile ⇒ no such requirement.
- **Judge robustness:** stub the LLM to return malformed JSON ⇒ neutral score + note, overall
  still computed.
- **CI harness:** a fixture below baseline ⇒ non-zero exit; all at/above ⇒ zero.
- api tests via `./run.sh` (arm64).

## Migration / rollout

1. `quality/rubric.py` deterministic core (reusing existing validators) + `RubricResult` shape.
2. Method-keyed criteria table + institution overlay (read a default profile).
3. LLM-judge dimensions.
4. Advisor-directive dimension (reads `advisor_feedback`, default `[]`).
5. `review_thesis` tool + M5 `review` roadmap sub-step.
6. `quality/eval_harness.py` + fixtures + CI wiring.

Steps 1–5 ship the student grader; step 6 is the internal harness.

## Dependencies

- **Spec 1** (chapter-scoped `assess_export_readiness`) — structural dimension.
- **Spec 2** (roadmap) — the M5 `review` sub-step + turning open directives into blockers.
- **Cross-session-memory spec** — owns `institution_profile` + `advisor_feedback` population;
  this spec reads them with safe defaults (see `project_advisor_feedback_loop` memory).
