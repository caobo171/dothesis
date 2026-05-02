# Humanizer v12 — M23 + M24 Parked

**Date:** 2026-05-02
**Branch:** master
**Production state:** v10.1 (M21) — UNCHANGED. Both M23 and M24 parked in the registry as references like other eliminated methods.

This is a clean stopping point. Resume from here without re-reading the full conversation.

---

## What was tried

Two new methods, both follow-ups to the v11 handoff's "5 weak registers" finding (T3 argument, T7 long essay, T8 how-to, T9 news, T11 memo plateaued at Sapling ~100 under M21).

Source signals: a Medium piece on invisible-Unicode tricks (rejected — see spec) and a YouTube humanization tutorial proposing six manual rewrite rules. Of the six, four were mechanically measurable and adopted: hedging rate, fronted-clause sentence openings, no-expansion (simplification proxy), and avoiding "X and Y" two-item lists.

### M23 — anchor + 4 rules in rewrite prompt + deterministic critic + 1 revision pass

`backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts`

Pipeline: strip → router → rewrite (with rules) → deterministic rule_compliance critic → if violations, ONE Gemini revision call with quantitative feedback ("you used 7 X-and-Y lists, target ≤2") → polish (unchanged from M21) → strip. 3 LLM calls best case, 4 worst case.

Critic implementation: `backend/src/services/humanizer/critic/rule_compliance.ts` — pure-function checker. Tests: `backend/scripts/test/test-rule-compliance.ts` (12/12 pass).

### M24 — M23 minus the critic + revision step (rules-only)

`backend/src/services/humanizer/methods/M24_rules_no_critic.ts`

Built after the M23 bench cross-tabulation showed all M23 catastrophic regressions occurred when the critic fired. Pipeline: strip → router → rewrite (with rules) → polish → strip. 3 LLM calls. No critic, no revision.

---

## Bench results

Sapling judge only (Copyscape out of credit). Single-run, no seed averaging.

| Text | Tone | M21 sap_in→out | M23 sap_in→out | M24 sap_in→out | Status |
|---|---|---:|---:|---:|---|
| **Failing in v11** | | | | | |
| T3 | argumentative | 100→100 | 100→100 | 100→100 | unchanged |
| T7 | long essay | 100→100 | 100→100 | 100→99 | unchanged |
| T8 | how-to | 98→100 | 98→100 | 98→100 | unchanged |
| T9 | news article | 100→100 | **100→1** | 100→99 | M23 hit, M24 missed |
| T11 | business memo | 100→100 | 100→100 | 100→100 | unchanged |
| **Passing in v11** | | | | | |
| T1 | academic lit | 100→9 | 100→0 | 100→0 | both improved |
| T2 | technical | 100→10 | **100→100** | 100→5 | M23 broke, M24 fine |
| T4 | conversational | 100→99 | 100→6 | 100→2 | both fixed (T4 was actually weak in this run; M21 baseline 99 vs v11 1 — variance) |
| T5 | formal report | 100→15 | 100→22 | **100→99** | M24 broke this one |
| T6 | short paragraph | 100→1 | **100→97** | 100→0 | M23 broke, M24 fine |
| T10 | personal | 100→1 | 100→1 | 100→1 | unchanged |
| T12 | product review | 100→0 | 100→1 | 100→0 | unchanged |

### Mean Sapling drops

- **Failing texts (T3,T7,T8,T9,T11):** M21=−0.4, M23=19.4, M24=0.0 (M24 vs M21 advantage: +0.4)
- **Passing texts (T1,T2,T4,T5,T6,T10,T12):** M21=80.7, M23=67.6, M24=84.7 (M24 vs M21 advantage: +4.0)
- **Total points across 12 texts:** M21=563, M24=593 (+30 advantage in aggregate, but driven by single-text wins balanced against single-text losses)

### Critic firing pattern (M23)

The critic fired on 6/12 texts. Cross-tabulation of when the critic fired vs whether M23 won/lost vs M21:

| Critic fired? | Wins vs M21 | Losses vs M21 |
|---|---|---|
| **No** (rules-only effectively) | T1, T4, T12 | none |
| **Yes** (rules + revision) | T9 | T2, T5, T6 |

Every M23 catastrophic regression occurred when the critic fired. Every M23 win on a previously-passing text came when the critic did NOT fire. M23's only failing-text win (T9) was the critic doing the work — the rules alone (M24) couldn't reproduce it.

---

## Why neither variant ships

**Per the spec's ship criteria** (`docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md`):

1. **Mean Sapling drop on 5 failing texts ≥ 30 points better than M21.** M23 = +19.8 (FAIL). M24 = +0.4 (FAIL).
2. **All 7 currently-passing texts stay under Sapling 15.** M23 broke T2 (10→100), T6 (1→97), T5 (15→22) — 3 regressions (FAIL). M24 broke T5 (15→99) — 1 regression (FAIL).

Neither variant satisfies both criteria.

---

## What this rules out

The spec's central hypothesis was: **"explicit rewrite rules + deterministic compliance critic is the missing signal that period anchors alone don't encode."** The data falsifies it on three fronts:

1. **The four rules don't move the failing registers.** T3, T7, T8, T11 all stayed at ~100 under both M23 and M24. The rules attack patterns (sentence rhythm, hedging density, parallel-pair frequency) that detectors don't actually use to flag those specific registers. The detectors are flagging *topic-vocabulary fingerprinting*, which no amount of structural rewriting can shift on its own.

2. **The critic+revision step's only big win came from stochastic revision variance, not from rule application.** When M24 removed the revision step, T9's 100→1 win disappeared. The revision call is essentially a second creative draft — sometimes it lands, sometimes it doesn't. That's noise, not signal.

3. **Adding constraints to the rewrite prompt introduces new variance even on the texts the rules don't help.** M24 broke T5 (15→99) without any critic involvement. The LLM's attention budget for the prompt is finite; making the prompt longer and more prescriptive degrades reliability on edge cases.

The YouTube tutorial techniques likely work in *manual* application because the human writer applies them with judgment about register, audience, and meaning. Encoded as prompt rules + a regex critic, they fire when they shouldn't and miss when they should.

---

## What this DOES NOT rule out

The v11 handoff's untested paths remain valid:

1. **Drop the `argumentative` anchor (Mill 1859) — never tested.** Mill consistently fails T3. ~5 min experiment: comment out the entry in M21's ANCHORS array, re-bench. The router would fall back to `academic_formal` for argumentative inputs (which got T3 → 21 in earlier tests).

2. **Add 1–2 more period anchors covering the failing registers.**
   - Frederick Douglass speech excerpt for argument
   - Mark Twain essays for narrative variety
   - Theodore Roosevelt addresses for memo / formal-business register
   Source from Project Gutenberg. Each anchor is ~3 paragraphs, ~300 words.

3. **Per-user anchor (Tier 2 monetization).** Add `userAnchor?: string` parameter. Premium feature; addresses the topic-vocabulary fingerprinting problem at its root by anchoring on the user's own non-LLM voice.

These address the *actual* failure mode (modern web-corpus topic-saturation in the failing registers) rather than the structural-features hypothesis that v12 falsified.

---

## Files retained for reference

```
backend/src/services/humanizer/
├── methods/
│   ├── M21_router_anchor.ts                    # production (untouched)
│   ├── M23_rules_critic_anchor.ts              # NEW — parked
│   ├── M24_rules_no_critic.ts                  # NEW — parked
│   └── index.ts                                # registers M23 + M24 (no production swap)
└── critic/
    └── rule_compliance.ts                      # NEW — parked

backend/scripts/test/
└── test-rule-compliance.ts                     # NEW — 12/12 pass via ts-node

bench-results/
├── v12-m23-failing-only.json                   # NEW — M21 vs M23 on T1-T12, Sapling
├── v12-m24-rules-only.json                     # NEW — M24 on T1-T12, Sapling
└── (other v8-v11 files unchanged)

docs/superpowers/
├── specs/2026-05-02-humanizer-m23-rules-critic-design.md   # NEW
├── plans/2026-05-02-humanizer-m23-rules-critic.md          # NEW
└── handoff/2026-05-02-humanizer-v12-m23-results.md         # NEW (this file)
```

---

## Commit history (this branch of work)

```
e3d9cb7  feat(humanizer): rule-compliance checker for M23 critic
d4efd4a  fix(humanizer): tighten M23 rule_compliance heuristics  (review fixes)
56f891d  test(humanizer): assertion script for rule_compliance checker
bb6aef1  feat(humanizer): M23 method — anchor + rules + critic + revision
0d11c6a  fix(humanizer): M23 review fixes — fallback anchor, drift watch, prompt clarity
5a4a650  feat(humanizer): M24 — M23 minus critic+revision (rules-only variant)
```

---

## What the next session should start with

1. **First:** Drop the `argumentative` anchor and re-bench. ~5 min. If T3 improves to ≤21 (per earlier tests), this is a free win and ships immediately.
2. **Then:** Add the 1–2 period anchors above. Source, format, register-test.
3. **Eventually:** Per-user anchor as a Tier 2 feature.

Skip:
- More rules-based experiments (falsified by v12)
- LLM-critic loops on the question "is this still AI?" (falsified by M1/M2/M9 in v9)
- Sapling-in-pipeline (forbidden by project preference)
- Wikipedia / CC-licensed modern web anchors (falsified by v11 Tier 1)
- Back-translation layered after anchors (falsified by M22 in v11)
- Invisible-Unicode tricks (rejected in v12 spec — brittle, ethically dicey)

The v11 handoff's "Path 1, 2, 3" is the right direction.
