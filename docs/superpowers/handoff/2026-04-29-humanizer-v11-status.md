# Humanizer v11 — Handoff Status

**Date:** 2026-04-29
**Branch:** `feat/humanizer-v8-bakeoff` (pushed to origin)
**Production state:** v10.1 (M21 router-anchor) wired in `humanizer.service.ts`, Copyscape failures non-fatal.

This is a clean stopping point. Next sessions can resume from here without re-reading the full conversation.

---

## Where things stand

### Architecture (production)

```
Input
  │
  ▼
HumanizerService.humanizePipeline()
  │
  ├─ Copyscape input score (best-effort, returns null on failure)
  │
  ▼
M21 router-anchor pipeline (backend/src/services/humanizer/methods/M21_router_anchor.ts)
  │  1. strip AI-vocab from input (deterministic, free)
  │  2. Gemini router picks 1 anchor from {academic_formal, academic_casual,
  │     argumentative, instructional, user_modern, user_narrative}
  │  3. Gemini rewrite anchored on the chosen one
  │  4. GPT polish anchored on the same
  │  5. strip AI-vocab from output
  │
  ▼
Copyscape output score (best-effort, returns null on failure)
```

3 LLM calls per humanize. ~$0.002–0.005 per request.

### Anchor library (active in M21)

| Anchor | Source | License | Register |
|---|---|---|---|
| `academic_formal` | Russell, *Problems of Philosophy* (1912) | Public domain | Abstract analytical / scientific exposition |
| `academic_casual` | James, *Talks to Teachers* (1899) | Public domain | Lecture / educational mid-formality |
| `argumentative` | Mill, *On Liberty* (1859) | Public domain | Polemic / arguing a position |
| `instructional` | Strunk, *Elements of Style* (1918) | Public domain | How-to / tutorial / business-formal |
| `user_modern` | Project owner's reflective writing | Self-supplied | Modern opinion / reflection |
| `user_narrative` | Project owner's personal narrative | Self-supplied | Modern personal story / experience |

### Key empirical principle (the most important finding)

**Anchors must be statistically OUTSIDE the LLM training distribution** to defeat detectors trained on LLM outputs. Validated by experiment:

- Period public-domain works (Russell, Mill, James, Strunk) — pre-1928, outside corpus → **work**
- Project owner's idiosyncratic writing (with typos like "casstle", "calmful") — unique-to-author → **works**
- Wikipedia / CC-licensed modern web text — heavily IN the LLM training corpus → **fails catastrophically** (the v11 Tier-1 experiment, see `bench-results/v11-tier1.json` — drops collapsed across the board)

This rules out generic web-scraped anchor sources. Future anchors should come from either pre-1928 PD works or per-user uploads.

### Bench results — current state (v10.1 / M21)

12-text corpus (`backend/scripts/bench/corpus/T1.txt` … `T12.txt`). Sapling judge (Copyscape out of credit at time of writing).

| Text | Tone | Sapling out | Status |
|---|---|---:|---|
| T1 | academic lit. review | 4 | ✓ |
| T2 | technical explainer | 0–3 | ✓ |
| T3 | argumentative essay | 99–100 | ✗ |
| T4 | conversational blog | 0–1 | ✓ |
| T5 | formal report | 0–6 | ✓ |
| T6 | short paragraph | 0–2 | ✓ |
| T7 | long essay | 62–94 | ✗ |
| T8 | how-to tutorial | 100 | ✗ |
| T9 | news article | 0–100 (variance) | ⚠️ |
| T10 | personal story | 1–4 | ✓ |
| T11 | business memo | 100 | ✗ |
| T12 | product review | 0–1 | ✓ |

**7 of 12 reliably pass strict Sapling. 5 weak registers: T3, T7, T8, T9, T11.**

### Why those 5 fail

All 5 share one trait: **modern web-corpus-saturated registers**. Argumentative essays, formal news, business memos, generic tutorials, and long expository essays are saturated in LLM training data, so even a perfect period-anchor mimic can't shift the topic-vocabulary fingerprint that detectors learned.

The `argumentative` anchor (Mill 1859) consistently fails on T3 — the period polemic voice on a modern AI/policy topic creates temporal mismatch the detector catches. Strunk on T8 (how-to) and T11 (memo) — the instructional voice transfers but the topic vocabulary still pings.

The architecture has plateaued without one of: (a) per-user voice anchors, (b) Sapling-in-pipeline adversarial loop, (c) more period anchors covering the failing registers.

---

## What was tried and what's parked

| Method | Status | Notes |
|---|---|---|
| **M21 (router-anchor)** | **Production** | Default v10.1 pipeline. |
| M0 v7 baseline | Eliminated | Mean Sapling drop 16, mostly useless. |
| M1 diagnostic critic | Eliminated | Δ ~0. |
| M2 self-critique | Eliminated | Δ ~1. |
| M3 adversarial proxy | Eliminated | Δ ~0 (LLM proxy doesn't predict Sapling). |
| M4 burstiness forcer | Eliminated | Δ ~0. |
| M5 n-best | Eliminated | Δ ~0 (stylometric scorer ≠ detector signal). |
| M6 sentence-surgical | Eliminated | Δ ~0. |
| M7 voice-anchor (4 anchors parallel) | Superseded by M21 | Won v8 bake-off but stylometric picker is unreliable. |
| M8 combo M1+M2+M4 | Eliminated | Δ ~0 (later passes undo gains). |
| M9 real adversarial loop | Eliminated | Bypassed because user forbids Sapling-in-pipeline. |
| M11 back-translation | Component of M22 | Useful as layered attack. |
| M12 disfluency injection | Eliminated | Δ ~2 (post-process alone is too small). |
| M15 M7→M11 | Tested | Best Copyscape Δ but Sapling Δ only 4. |
| M16 first-person reframe | Eliminated | Δ ~0. |
| M17 anti-AI-vocab | Used inside M21 | The strip-vocab utility from M17 is now part of M21. |
| M18 anchor mixing | Eliminated | Marginal. |
| M19 strip→M7→strip | Superseded by M21 | M21 is M19 with a router instead of stylometric scorer — strictly better. |
| M20 M7→M9 | Eliminated | Sapling-in-pipeline cost. |
| **M22 (M21 → M11 layered)** | **Built and tested — REGRESSION, do not use** | Back-translation undoes the anchor. T4 went 1→100, T5 went 0→100, T10 went 1→100, T12 went 1→100. The French→English roundtrip strips the period-anchor stylistic fingerprint and returns the text to LLM-distribution English. Confirmed: anchor mimicry and back-translation are incompatible attacks; layering them cancels both. |

Method files live at `backend/src/services/humanizer/methods/M*.ts`. Eliminated methods are kept for posterity; only the imports in `methods/index.ts` matter for the running pipeline.

---

## Cost picture (production v10.1)

| Item | Cost per humanize |
|---|---|
| Gemini router call | ~$0.0002 |
| Gemini anchored rewrite | ~$0.0008 |
| GPT polish | ~$0.0015 |
| **Total LLM** | **~$0.0025** |
| Copyscape input + output (when not exhausted) | ~$0.06 each call |
| Sapling judge (NOT in pipeline; bench only) | ~$0.005 per call |

The Copyscape calls dominate cost when used. Production currently treats Copyscape as a best-effort UI badge — humanize works regardless of detector availability.

---

## Future-development checklist

The next session should pick up from any of:

1. **Drop the `argumentative` anchor.** Mill 1859 consistently fails T3. Run M21 without it and see if the router falls back to `academic_formal` (which got T3 → 21 in earlier tests, much better than 99). One-line fix: comment out the entry in `M21_router_anchor.ts` ANCHORS array. ~5 min experiment.

2. **Add 1–2 more period anchors** from public domain to fill the `instructional` and long-form gaps:
   - Frederick Douglass speech excerpt for argument
   - Mark Twain essays for narrative variety
   - Theodore Roosevelt addresses for memo / formal-business register
   Source from Project Gutenberg. Each anchor is ~3 paragraphs, ~300 words. Same pattern as existing files.

3. **Per-user anchor (Tier 2 monetization).** Add `userAnchor?: string` parameter to `humanizePipeline`. If set, the router prefers it (or skips routing entirely and uses just that anchor). UI flow: user pastes 100w of their own writing once, saved to profile. Premium feature; doesn't compete with Tier 1, just makes output sound *like them*. Real moat.

4. **Top up Copyscape** to restore in-pipeline scoring. Currently `checkAiScore` returns null on failure (non-fatal), so the badge just disappears. Topping up restores it. Or swap to Sapling-as-judge in production (would cost ~$0.005 per humanize for the score badge).

5. **M22 was tested and failed.** Catastrophic regression on the working texts (T4/T5/T10/T12 went 0–1 → 100). Back-translation cannot be layered after voice-anchoring — they cancel. **v10.1 (M21) is the v11 final state.** Don't try this layering again. If a session wants to combine attacks, the order would have to be reversed (back-translate first, anchor second) but that's a v12 experiment and probably also doesn't work for the same distributional reason.

6. **NEVER do this:** add Wikipedia / CC-licensed modern web content as anchors. Validated by the v11 Tier-1 experiment to make things catastrophically worse — anchors must be outside the LLM training distribution.

---

## Quick commands for the next session

```bash
# Branch
cd /Users/caonguyenvan/project/dothesis
git checkout feat/humanizer-v8-bakeoff
git pull

# Run M21 (v10.1 production) on the corpus, Sapling-only
cd backend
npx ts-node -r tsconfig-paths/register scripts/bench/dual-judge-bakeoff.ts \
  --methods M21 --out ../bench-results/check.json --no-copyscape

# Run M22 (v11.2 candidate)
npx ts-node -r tsconfig-paths/register scripts/bench/dual-judge-bakeoff.ts \
  --methods M22 --out ../bench-results/check22.json --no-copyscape

# Run a single text (faster iteration)
npx ts-node -r tsconfig-paths/register scripts/bench/humanizer-bench.ts \
  --method M21 --text T8 --copyscape false --sapling true \
  --out /tmp/quick-test.json

# End-to-end smoke (uses production HumanizerService)
npx ts-node -r tsconfig-paths/register scripts/smoke-v8.ts
```

Bench output JSON shape: array of `BenchRecord` (see `backend/src/services/humanizer/methods/types.ts`). Use `python3` or `jq` to summarize.

---

## Files of interest

```
backend/
├── src/services/humanizer/
│   ├── humanizer.service.ts            # production entry point
│   ├── methods/
│   │   ├── index.ts                    # method registry (which methods are loaded)
│   │   ├── types.ts                    # BenchRecord, MethodResult, MethodOptions
│   │   ├── M21_router_anchor.ts        # current production
│   │   ├── M22_router_then_backtrans.ts # v11.2 candidate (in flight)
│   │   └── M*.ts                       # eliminated methods, kept for reference
│   ├── postprocess/
│   │   ├── anti_ai_vocab.ts            # used inside M21
│   │   └── disfluency.ts               # not currently in use
│   └── critic/, stylometric/, burstify/  # utilities used by eliminated methods
└── scripts/bench/
    ├── corpus/T{1..12}.txt             # 12-text test corpus
    ├── anchors/                        # 6 active anchor files + extras
    ├── humanizer-bench.ts              # single-method/single-text harness
    ├── dual-judge-bakeoff.ts           # multi-method × multi-text driver
    ├── fill-sapling.ts                 # post-hoc Sapling fill on saved JSON
    └── generate-corpus.ts / generate-corpus-v2.ts  # corpus generators

bench-results/
├── M0.json … M8.json                   # individual method results from v8 bake-off
├── v8-final.json                       # M7 sweep on T1-T5
├── v8.1-with-sapling.json              # M7 with both judges
├── v9-final.json                       # 10 methods M0-M8 dual-judge
├── v9.1-with-user-anchor.json          # M7+M19 with user_modern
├── v10-router.json                     # M21 first run
├── v10.1-narrative.json                # M21 with user_narrative
├── v10.1-extended.json                 # M21 on T1-T12
├── v11-tier1.json                      # FAILED — Wikipedia anchors
├── v11.1.json                          # M21 with Strunk added
├── v11.2-m22.json                      # M22 in flight
├── round1-summary.md                   # v8 bake-off elimination
└── comparison.md                       # v8 final comparison

docs/superpowers/
├── specs/2026-04-28-humanizer-method-bakeoff-design.md
├── plans/2026-04-28-humanizer-method-bakeoff.md
└── handoff/2026-04-29-humanizer-v11-status.md  ← THIS FILE
```

---

## What the user wants for the next session (per stated preferences)

- **No Sapling in the pipeline.** Per-request cost too high.
- **No per-user anchor required at MVP.** Wants scale.
- **No Wikipedia/web-scraped modern anchors.** (Even before they knew this — confirmed by v11 Tier-1 failure.)
- **Period anchors fine. Per-user anchors as premium feature is fine.**
- **Pragmatic over perfect.** They've signalled "ship and iterate" repeatedly.

Default the next session to: investigate paths 1, 2, 3 above in that order. Skip path 4 (Copyscape topup) unless explicitly asked.
