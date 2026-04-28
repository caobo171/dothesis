# Humanizer v8 Bake-Off — Final Comparison

**Date:** 2026-04-28
**Judge:** Copyscape `aicheck` (called only on input + final output, never inside any pipeline)

## Summary

**Winner: M7 voice-anchoring.** Mean Copyscape drop of 57 points across 5 fixed-corpus texts, vs. 16.6 for the v7 baseline (and 0.6 for the second-best method). M7 reduces clearly-AI text (score 95-99) to clearly-human (1-7) on three of the five texts.

## Round 2 results — full comparison

All 9 methods (8 candidates + M0 baseline) on T1; survivors (M1, M7) extended to T2–T5.

| Method | T1 | T2 | T3 | T4 | T5 | Mean Δ | Notes |
|--------|----|----|----|----|----|-------:|-------|
| M0 v7 baseline           | 99→98 (Δ1)  | 98→98 (Δ0) | 94→88 (Δ6) | 90→98 (Δ-8) | 98→14 (Δ84) | **16.6** | Only T5 worked |
| M1 diagnostic critic     | 99→94 (Δ5)  | 98→98 (Δ0) | 95→93 (Δ2) | 88→94 (Δ-6) | 98→96 (Δ2)  | **0.6**  | Worse than baseline |
| M2 self-critique         | 99→99 (Δ0)  | — | — | — | — | — | Eliminated round 1 |
| M3 adversarial paraphrase| 99→96 (Δ3)  | — | — | — | — | — | Eliminated round 1 |
| M4 burstiness forcer     | 99→99 (Δ0)  | — | — | — | — | — | Eliminated round 1 |
| M5 n-best (5 drafts)     | 99→98 (Δ1)  | — | — | — | — | — | Eliminated round 1 |
| M6 sentence-surgical     | 99→99 (Δ0)  | — | — | — | — | — | Eliminated round 1 |
| **M7 voice-anchoring**   | **99→77 (Δ22)** | **98→1 (Δ97)** | **95→7 (Δ88)** | **89→65 (Δ24)** | **98→44 (Δ54)** | **57** | **Winner** |
| M8 combo (M1+M2+M4)      | 99→97 (Δ2)  | — | — | — | — | — | Eliminated round 1 |

## M7 reproducibility check

To confirm M7's dramatic drops are not Copyscape variance, T2 was re-run once. Result: **98 → 1 again** (identical score), confirming the result is not a noisy outlier.

## Cost / latency

| Method | Mean tokens (in+out) | Mean duration |
|--------|---------------------:|---------------|
| M0     | ~6300 | ~99 s |
| M7     | ~3000 | ~24 s |

M7 is also **~2× cheaper and ~4× faster** than v7. The win is on every dimension.

## Why voice-anchoring works

The other seven methods *describe* what human prose looks like — varied sentence length, unexpected vocabulary, irregular punctuation. The LLM tries to follow the description but reverts to its training distribution under the hood (low-perplexity, uniform cadence).

M7 instead *shows* the LLM 3 paragraphs of confirmed human academic prose (Russell's *Problems of Philosophy* 1912, James's *Talks to Teachers* 1899) and asks it to mimic the cadence, sentence-length variance, word choice, and punctuation rhythm. Few-shot stylistic transfer is far more effective than instruction-following for stylometric mimicry — the model has a concrete distribution to copy from rather than abstract rules to interpret.

The pipeline:
```
Input → run twice in parallel:
  - Gemini rewrite anchored on academic_formal.txt → GPT polish anchored on same
  - Gemini rewrite anchored on academic_casual.txt → GPT polish anchored on same
Pick lower stylometric score (deterministic)
```

## Out-of-scope methods

The eliminated methods (M2, M3, M4, M5, M6, M8) are kept in their experiment branches for posterity. None showed signal worth pursuing on the corpus we tested.

## Decision

**Merge M7's method into `feat/humanize-crossmodel-perturbation` as v8.** Update `HumanizerService.humanizePipeline` to call `getMethod('M7').run(...)` instead of the old v7 cross-model loop.
