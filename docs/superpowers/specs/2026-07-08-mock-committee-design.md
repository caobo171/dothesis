# Mock Committee (Hội đồng ảo) Design (F6)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Relationship:** The emotional peak of the student journey and the shareable/referral moment.
A post-M5 defense-prep flow that reuses earned state + the quality rubric (F3) findings as its
question source. Not a new state-machine module (keeps `MODULES` = M1–M5 unchanged).

## Problem

Students finish the thesis and walk into a defense unprepared — they can't answer for their own
weak points (borderline HTMT, small n, rejected hypotheses, convenience sampling). No competitor
generates defense questions from *this student's actual* weaknesses. It's also the moment a
satisfied student refers friends.

## Goals

- **Weakness-targeted questions:** generate 20–30 committee questions derived from this thesis's
  real weak points (from rubric findings + earned state), not generic ones.
- **Interactive drill:** the agent asks, the student answers, the agent grades and coaches a
  stronger answer.
- **Defensible cheat-sheet:** a one-paragraph, citable response per weakness the student can
  study.
- **Preempt in the thesis:** optionally feed the found weaknesses into the M5 limitations section
  so they're disclosed, not ambushed.

## Non-goals

- Not a new tracked module (no `MODULES`/state-machine change) — it's an optional skill invoked
  after M5, surfaced as a roadmap card once M5 is done.
- Not a grader of the thesis (F3 does that) — it consumes F3's findings.

## Design

### Skill

- `skills/dothesis-defense/SKILL.md` — the flow: gather weak points → generate questions →
  drill → cheat-sheet. Invoked when the user asks to prep for defense, or offered as a roadmap
  card after M5 is `done`.

### Tool

- `generate_committee_questions(context_store, rubric_result=None) -> str` in
  `agent/tools/defense.py`: reads earned state (small n, rejected hypotheses, method choices,
  sampling method, borderline validity) + optional F3 `RubricResult.findings`, and produces
  categorized questions `[{category, question, targets, difficulty, model_answer_hint}]`.
  Categories: methodology, results/validity, contribution, limitations, theory.
- If no `rubric_result` is passed, it calls F3's `score_thesis` itself (soft dependency) or
  falls back to state-only heuristics.

### Interactive drill + cheat-sheet

- Drill is agent-driven via the skill (ask → student answers → agent grades vs.
  `model_answer_hint` → coach). No new tool needed — the skill orchestrates it.
- Cheat-sheet: the skill compiles the drilled answers into a `defense_cheatsheet` artifact,
  exportable via the existing DOCX/`run_export` path (a short standalone document).

### Roadmap surfacing (F2)

- When M5 is `done`, `next_action` (F2) offers "Prep for your defense" as the next action
  (a post-completion step), rendering a CTA that invokes the defense skill. No `roadmap_tasks`
  or MODULES change — it's an optional terminal step.

### Preempt into limitations (optional)

- The found weaknesses can be handed to M5 to draft/strengthen the limitations section
  ("turn the weakness into a disclosed, cited limitation").

## Data flow

```
M5 done → next_action offers "Prep for your defense"
  → defense skill → generate_committee_questions(store, rubric)
  → interactive drill (ask/grade/coach) → defense_cheatsheet (export)
  → optional: feed weaknesses into M5 limitations
```

## Error handling

- `generate_committee_questions` best-effort: if the LLM/rubric fails, fall back to state-only
  heuristic questions (small n, rejected H, sampling) so the drill always has material.
- Read-only over thesis state (except the optional, explicit limitations write via M5's normal
  path).

## Testing

- `generate_committee_questions`: a state with n=90 + a rejected hypothesis ⇒ questions that
  target sample size and the rejected hypothesis; empty rubric ⇒ still returns state-based
  questions.
- Robustness: stubbed LLM failure ⇒ heuristic fallback returns ≥ some questions.
- Skill mentions the tool and the drill protocol (grep).
- Cheat-sheet exports via `run_export` (reuse existing export test patterns).
- api tests via `./run.sh`.

## Migration / rollout

1. `generate_committee_questions` tool (state-only heuristics first).
2. Rubric-informed question generation (consume F3 findings).
3. `skills/dothesis-defense/SKILL.md` drill + cheat-sheet export.
4. F2 `next_action` post-M5 "defense" offer.
5. Optional limitations-preempt hook into M5.

## Dependencies

- **F3** (quality rubric) — findings are the best question source; sequence Mock Committee right
  after F3 ships. Works state-only without it.
- **F2** (roadmap) — the post-M5 "defense" offer in `next_action`.
- Existing `run_export` for the cheat-sheet.
