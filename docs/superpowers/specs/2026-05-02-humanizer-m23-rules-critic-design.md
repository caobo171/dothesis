# M23 — Rules-Critic-Augmented Anchor Pipeline (Humanizer v12 candidate)

**Date:** 2026-05-02
**Status:** Design approved, awaiting implementation plan
**Branch:** `feat/humanizer-v8-bakeoff` (continues v11 work)
**Predecessor:** v10.1 / M21 (`backend/src/services/humanizer/methods/M21_router_anchor.ts`) — 7/12 corpus texts pass strict Sapling
**Related:**
- v11 handoff: `docs/superpowers/handoff/2026-04-29-humanizer-v11-status.md`
- bake-off spec: `docs/superpowers/specs/2026-04-28-humanizer-method-bakeoff-design.md`

---

## Goal

Lift the 5 weak registers (T3 argumentative, T7 long essay, T8 how-to, T9 news, T11 business memo) by injecting four explicit rewrite rules into M21's anchored Gemini stage, with a deterministic compliance critic that forces actual rule application via one revision pass.

The 5 failing registers are all modern-web-saturated topic spaces where period-anchor mimicry alone can't shift the topic-vocabulary fingerprint detectors learned. Rules attack a different signal: structural patterns (hedging, sentence opening variation, simplification, anti-parallel-list) that AI-detection literature and human-rewrite practitioners both flag as the highest-signal humanization techniques.

## Non-goals

- Not changing the anchor library
- Not adding per-user anchors
- Not putting Sapling in the production pipeline (per project preference)
- Not adding fabricated in-text citations (rejected: hallucination risk worse than the detection problem we're solving)
- Not adding critique/multi-perspective injection (rejected: changes user's argument, not just form)
- Not invisible-Unicode tricks (rejected: project already strips watermarks; brittle against modern detectors; brand/ethics)
- Not modifying M21 production behavior until M23 wins the bench

## Source signals

Two external sources informed the rule selection:

1. A Medium piece advocating an invisible-Unicode/white-text trick — **rejected**, see Non-goals.
2. A YouTube humanization tutorial proposing six manual rewrite techniques. Of those six:
   - **Adopted:** intellectual hedging, fronted-clause sentence openings, aggressive simplification, breaking the "X and Y" two-item list rhythm.
   - **Rejected:** in-text citations (fabrication risk), subtle critique (alters user's argument).

The four adopted rules share one critical property: each is **mechanically measurable** with deterministic checks, no LLM critic required. This is what makes the deterministic critic phase viable.

## Architecture

```
Input
  │
  ▼
strip AI-vocab (deterministic, free — reused from M17)
  │
  ▼
Gemini router picks anchor (unchanged from M21)
  │
  ▼
Gemini anchored rewrite WITH RULES INJECTED in the prompt
  │
  ▼
Deterministic rule-compliance critic
  ├── pass → continue
  └── fail → ONE revision call to Gemini with quantitative feedback
              (e.g. "you used 7 X-and-Y lists, target ≤2;
                     only 1 fronted-clause sentence, target ≥3 per 12 sentences")
              → continue (do NOT loop further; one revision attempt only)
  │
  ▼
GPT polish (UNCHANGED from M21 — keep polish pure to avoid undoing rule work)
  │
  ▼
strip AI-vocab (deterministic, free)
  │
  ▼
Output
```

**LLM call budget:** 3 (best case, no revision triggered) or 4 (revision triggered). Cost ~$0.0025–0.0035, comparable to M21's $0.0025.

**Why one revision attempt only, not a loop:** longer loops drift quality and inflate cost without bound. One revision with quantitative feedback is the cheapest insurance against the "LLM acknowledged the rule but didn't apply it" failure mode the user raised.

## The four rules and their measurable thresholds

| # | Rule | Measure | First-cut threshold |
|---|---|---|---|
| 1 | **Hedging** | Count of hedge tokens: `appears`, `seems`, `may`, `might`, `can`, `suggests`, `is believed`, `is suspected`, `is likely`, `tends to`, `arguably`, `presumably` | ≥ 2 per 100 words |
| 2 | **Fronted-clause openings** | Count of sentences NOT starting with the subject NP — i.e. starting with a subordinator (`Although`, `While`, `Since`, `Because`, `Despite`, `Given`, `When`), present participle (`Considering`, `Looking`), or fronted PP (`In…`, `Across…`, `Under…`, `By…`) | ≥ 25% of sentences |
| 3 | **No expansion (simplification proxy)** | `output_word_count / input_word_count` | ≤ 1.05 |
| 4 | **Anti-"X and Y" two-item lists** | Regex for parallel two-item noun/adj conjunctions, excluding common idioms (`back and forth`, `more and more`, etc.) via stopword whitelist | ≤ 3 per 100 words |

Thresholds are first-cut and will be tuned during the bench based on what the M21 baseline already produces. Tuning is part of implementation, not a re-design.

## Components

### `backend/src/services/humanizer/critic/rule_compliance.ts`

Pure-function module. No LLM calls, no IO.

```ts
export type RuleViolation = {
  rule: 'hedging' | 'fronted_openings' | 'no_expansion' | 'anti_x_and_y';
  measured: number;
  threshold: number;
  feedbackForLLM: string;  // human-readable instruction for the revision call
};

export type ComplianceReport = {
  passed: boolean;
  violations: RuleViolation[];
  metrics: {
    inputWords: number;
    outputWords: number;
    hedgeCount: number;
    sentenceCount: number;
    frontedClauseCount: number;
    xAndYCount: number;
  };
};

export function checkRuleCompliance(input: string, output: string): ComplianceReport;
export function formatRevisionFeedback(report: ComplianceReport): string;
```

`formatRevisionFeedback()` produces the natural-language feedback that gets appended to the revision prompt, e.g.:
```
Your previous rewrite missed these targets:
- "X and Y" two-item lists: you used 7, target ≤2. Replace with single nouns or longer enumerations.
- Fronted-clause openings: you have 1 of 12 sentences (8%), target ≥25%. Start more sentences with "Although", "While", "Given", or fronted prepositional phrases.
Apply these fixes while preserving the original meaning.
```

### `backend/src/services/humanizer/critic/rule_compliance.test.ts`

Unit tests for the checker. TDD targets:
- `hedgeCount` correctly counts whole-word matches (no false positives on "Mayor", "scanning", etc.)
- `frontedClauseCount` correctly identifies fronted clauses on hand-crafted sentences
- `xAndYCount` whitelists common idioms (`back and forth`, `more and more`, `over and over`, `up and down`) but flags real two-item lists
- `formatRevisionFeedback` only mentions failed rules, not passed ones
- Threshold edge cases (exactly at threshold = pass, one below = fail)

### `backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts`

The method. Implements the `Method` interface from `methods/types.ts` so it works with the existing bench harness.

Reuses from M21:
- The router (anchor selection)
- The anchor library (no changes)
- The polish stage (no changes)
- The strip-AI-vocab pre/post passes

New:
- Rewrite prompt augmented with the four rules in explicit imperative form
- Critic call after rewrite
- Revision call (single attempt) when critic fails

Tracks `tokenSteps` for all calls including the revision so cost is visible in bench output.

### Refactor: `backend/src/services/humanizer/methods/M21_router_anchor.ts`

Extract the rewrite-prompt builder into a small exported helper so M23 can reuse it with rules appended. **No behavior change to M21.** Verified by: M21 bench output identical before vs. after refactor.

### Method registry: `backend/src/services/humanizer/methods/index.ts`

Add M23 to the registry so the bench harness can target it via `--methods M23`.

## What is NOT modified

- `backend/src/services/humanizer/humanizer.service.ts` — production stays on M21 until M23 wins the bench. After ship, the only change is replacing `getMethod('M21')` with `getMethod('M23')`.
- Polish prompt — keep polish pure to avoid GPT undoing the rules.
- Anchor files in `backend/scripts/bench/anchors/`.

## Bench plan and ship criteria

### Phase 1 — fast iteration (~5 min)
```bash
cd backend
npx ts-node -r tsconfig-paths/register scripts/bench/dual-judge-bakeoff.ts \
  --methods M21,M23 --texts T3,T7,T8,T9,T11 \
  --out ../bench-results/v12-m23-failing-only.json --no-copyscape
```
Both M21 and M23 in the same run for direct comparison on the failing subset. Tune thresholds if M23 looks promising but borderline; re-run.

### Phase 2 — verification before ship (~12 min)
```bash
npx ts-node -r tsconfig-paths/register scripts/bench/dual-judge-bakeoff.ts \
  --methods M21,M23 --out ../bench-results/v12-m23-full.json --no-copyscape
```
Full T1–T12. Confirms no regression on the 7 currently-passing texts.

### Ship criteria (must satisfy BOTH)
1. **Mean Sapling-out on the 5 failing texts (T3, T7, T8, T9, T11) drops by ≥ 30 points** vs the M21 baseline in the same run.
2. **The 7 currently-passing texts (T1, T2, T4, T5, T6, T10, T12) all stay under Sapling-out 15.**

### If ship criteria are met
- Swap `humanizer.service.ts` to call `getMethod('M23')` instead of `M21`.
- Update the version log comment in `humanizer.service.ts` from `v10.1` to `v12`.
- Commit and push.
- Write a v12 handoff doc summarizing the win and updating the failing-texts table.

### If ship criteria are NOT met
- Document findings (which rules helped, which didn't, threshold tuning history) in `docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md`.
- Park M23 in the registry (kept for reference like the other eliminated methods).
- Do NOT modify production.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM still doesn't apply rules even with explicit feedback | Single revision is bounded — worst case is +1 LLM call; we accept this and ship if criteria still met |
| Hedging makes T8 (how-to) and T11 (memo) sound less assertive, hurting tone fidelity | Bench measures Sapling, not tone — if Sapling improves, ship and re-evaluate via real-user feedback later |
| Threshold tuning becomes a rabbit hole | Time-box phase 1 to two threshold iterations; if neither converges, document and park |
| The rules-in-prompt change interacts badly with the existing anchor instruction (model gets confused with too many rules) | The rules are the *only* prompt change; anchor instructions stay verbatim. If output looks worse on the 7 passing texts in phase 2, that's the signal. |
| Rule checker has false-positive matches (e.g. "scanning" matches `\bcan\b` if someone writes a bad regex) | Unit tests cover this explicitly — checker is TDD'd before the method calls it |
| The single-revision call doubles latency on hard texts | Acceptable; humanize is not a real-time interaction. UI already shows staged progress. |

## Out-of-scope (explicit)

- Per-user anchors (Tier 2 monetization, separate spec when prioritized)
- Replacing Copyscape with another in-pipeline detector (separate decision)
- Sapling-in-pipeline adversarial loops (forbidden by project preference)
- Adding more period anchors (path 2 in v11 handoff — separate, parallel experiment)
- Dropping the argumentative anchor (path 1 in v11 handoff — separate, can be tried before or after M23)

## Success looks like

After phase 2:
- T3, T7, T8, T9, T11 mean Sapling drops from current ~80+ to ≤50 (≥30 point lift)
- T1, T2, T4, T5, T6, T10, T12 all stay under Sapling 15
- Production swapped to M23
- v12 handoff written
- Total time investment: ≤ 1 working session
