# Quantitative Correctness Content Pack Design (F8)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Relationship:** Extends the coaching layer (F2) — this is the *content* the agent leads
with. Feeds the quality rubric (F3) with new criteria. Mostly skill content + two small
deterministic checks; **no stats engine** (`project_agent_gaps` / `project_best_in_class_backlog`
memory).

## Problem

The agent leads step-by-step (F2) but its *quantitative correctness content* is thin. Novices
make predictable, fatal errors — wrong test for the design, unpowered samples, undetected
common-method bias, misread output tables — and only find out at defense. A good advisor
catches these while they're cheap. Today DoThesis doesn't encode that eye, and it explains
statistics at a level that intimidates stats-anxious students.

## Goals

Four cohesive additions, all guidance (content) except two thin deterministic checks:

1. **Design→Test Decision Matrix** — content that maps (model type + sample size + construct
   nature + data properties) → the correct method (PLS-SEM / CB-SEM / regression) with a
   citable justification. The agent must consult it before endorsing any analysis plan.
2. **Methods Pre-Flight Gate** — an advisory M3→M4 readiness check: sample size (10× + inverse-
   square-root), reverse-coded items flagged, a CMB/Harman plan, a missing-data plan, screening
   steps. Surfaced before M4 analysis; also a rubric criterion.
3. **Two-Register Explanations** — a root-skill style rule: every statistical concept is
   explained twice — (a) a plain-language Vietnamese analogy, (b) the formal sentence the
   student can paste into the thesis.
4. **Output Sanity Layer** — a per-table interpretation protocol (loadings, HTMT, Fornell-
   Larcker, VIF, bootstrap paths, R²/f²/Q², fit indices): check thresholds, flag borderline
   values, AND flag *suspiciously perfect* results (all loadings > 0.9, HTMT all < 0.5 ⇒ likely
   straight-lined data or wrong matrix). A thin `check_thresholds` tool + reference content.

## Non-goals

- No computation of statistics (the student's software computes; we interpret/audit).
- Not a hard gate — Methods Pre-Flight is advisory (consistent with "locked is a
  recommendation, not a wall"); it surfaces missing items, doesn't refuse.

## Design

### 1 & 4 — content assets

- `skills/dothesis-m3-design/references/design-test-matrix.md` — the decision tree + Hair-et-al
  thresholds + worked justifications. M3 skill gains a rule: "before endorsing an analysis plan,
  consult design-test-matrix and cite the rule that applies."
- `skills/dothesis-m4-analysis/references/output-interpretation.md` — per-table threshold table +
  the "suspiciously perfect" heuristics + how to narrate each in the Results chapter.

### 2 — Methods Pre-Flight

- `preflight_check(context_store) -> list[str]` in `agent/preflight.py` (pure, like
  `assess_export_readiness`): returns human-readable missing items from M3 state
  (`methodology`, `instrument`, sample-size target, reverse-coded flag, CMB plan, missing-data
  plan). Empty = ready.
- Surfaced by the M4 skill at the start of the analysis pipeline, and injected as an advisory
  line when `focus == M4` and items are missing. Added to the F3 rubric as a `preflight`
  criterion (soft).

### 3 — Two-Register

- A rule in `skills/dothesis/SKILL.md`: the dual-explanation template, applied product-wide.
  Content only.

### check_thresholds tool

- `check_thresholds(table_kind, rows) -> str` in `agent/tools/stats.py` (whitelisted-ops
  spirit): deterministic threshold classification + the suspiciously-perfect flags for a pasted
  table. Never computes new statistics — only classifies values the student already has.

## Data flow

```
M3: agent consults design-test-matrix → endorses method with citation
M3→M4: preflight_check(store) → advisory "before you run: fix N items"
M4: student pastes output → check_thresholds + output-interpretation ref → interpret + flag
everywhere: two-register explanation rule
F3 rubric: + preflight criterion
```

## Error handling

- `preflight_check` / `check_thresholds` are pure and total — never crash on partial input.
- Advisory only: missing pre-flight items never block M4 (surface + offer to fix).

## Testing

- `preflight_check`: fixtures missing sample size / reverse-coded flag ⇒ the right items;
  complete M3 ⇒ empty.
- `check_thresholds`: a good PLS loading table ⇒ no flags; all-loadings-0.95 ⇒ "suspiciously
  perfect" flag; HTMT 0.91 ⇒ discriminant-validity flag.
- Content: skills mention the new references and the two-register rule (grep).
- api tests via `./run.sh`.

## Migration / rollout

1. `design-test-matrix.md` + M3 skill rule (pure content; highest-leverage, ship first).
2. Two-register rule in root skill.
3. `preflight_check` + M4 skill surfacing + F3 rubric criterion.
4. `output-interpretation.md` + `check_thresholds` tool + M4 skill wiring.

## Dependencies

- **F2** (roadmap/coaching) — where the content is led from; the M4 advisory line uses the
  `[NEXT]`/state-header surface.
- **F3** (quality rubric) — gains the `preflight` criterion.
