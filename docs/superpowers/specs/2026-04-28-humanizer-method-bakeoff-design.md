# Humanizer v8: Method Bake-Off

**Status:** Approved design
**Parent branch:** `feat/humanize-crossmodel-perturbation`
**Date:** 2026-04-28

## Problem

Humanizer v7 (cross-model + perturbation + self-improvement loop) is not effective. On a 101-word academic input the pipeline reports `99 → 97` over four iterations — the self-improvement loop is *blind* (it perturbs and polishes without diagnosing why the score is stuck), so iterating produces no signal.

Two things are missing:

1. **A critical phase.** Without a diagnostic step that identifies *which* sentences/patterns still trigger the detector, every rewrite is a guess.
2. **Empirical validation.** We've been changing the pipeline by intuition. There's no benchmark, no comparison, no winner — just a single "current pipeline" that we hope is good.

## Goal

Run a controlled bake-off of 8 candidate humanizer pipelines against a fixed corpus, score each with Copyscape (judge only — never in the pipeline), and merge the winner as v8. Deliverable: a method we own end-to-end that beats v7 on Copyscape AI score by a wide margin, at a per-request cost lower than calling Copyscape itself.

## Design Principles

1. **Copyscape is the judge, not a tool.** No Copyscape calls inside any pipeline. Internal feedback uses LLM proxies or deterministic stylometric scorers. This keeps the runtime tech we own and our cost predictable.
2. **Diagnostic before rewrite.** Every method that can support it gets a "critical phase" — read the draft, identify what's still AI-flavored, then rewrite *targeting those findings*.
3. **Empirical, not vibes.** Each method runs on the same 5 inputs, judged by the same external scorer, with early elimination so losing methods don't burn budget.
4. **Soft cost ceiling.** Per-request token spend stays below Copyscape's per-call price. M5 / M8 may exceed this if they win significantly — case-by-case.

## What detectors actually score (background)

Per GPTZero / Copyscape / Originality public docs and recent literature:

- **Perplexity** — uniform/predictable next-token choice → AI signal. Humans pick unexpected words.
- **Burstiness** — variance of sentence length and complexity. AI averages 12–18 words with low σ; humans swing wildly (σ ≥ 7).
- **Stylometric fingerprint** — function-word ratio, punctuation entropy, type-token ratio, parallel-structure density.

Surface synonym swaps don't move these signals. The methods below attack them directly.

References:
- [Adversarial Paraphrasing — NeurIPS 2025](https://arxiv.org/abs/2506.07001) — paraphrase guided by detector signal drops detection 87.88% on average
- [DIPPER paraphraser](https://openreview.net/pdf?id=WbFhFvjjKj) — controlled lexical-diversity paraphrase
- [GPTZero on perplexity & burstiness](https://gptzero.me/news/perplexity-and-burstiness-what-is-it/)
- [Stylometry in AI detection](https://netus.ai/blog/stylometry-explained-how-ai-detectors-fingerprint-your-writing)

## The 8 Methods

Each method is a **complete pipeline**, not a layer. Each is implemented in its own worktree branched off `master` and produces a single `bench-results/MX.json` file.

### M1 — Diagnostic Critic

Replace v7's blind polish loop with a targeted diagnostic loop.

```
Input → Gemini rewrite → Perturb → GPT cross-rewrite →
  Loop (≤3):
    Gemini critic call: returns {aiTells: [{sentence, why}]}
    If aiTells empty → break
    Gemini targeted-rewrite: rewrite ONLY the flagged sentences with reasons attached
  → Final output
```

**Internal signal:** an LLM critic prompt. No Copyscape.
**Why it could work:** every rewrite has a stated reason. No more random perturbation.

### M2 — Self-Critique Loop

Same shape as M1 but the rewriter critiques *its own previous output* instead of using a separate critic prompt.

```
Input → Gemini rewrite (draft 1)
  Loop (≤3):
    Gemini self-critique: "Here is your previous draft. Identify 3-5 sentences
      that still sound AI-generated and explain why."
    Gemini rewrite-with-self-critique: rewrites against its own critique
  → Final output
```

**Why it could work:** forcing the model to justify changes pushes it past pattern-matching into deliberate edits.

### M3 — Adversarial Paraphrase (LLM-proxy guided)

Port the NeurIPS 2025 idea, replacing the real detector with an LLM proxy so we don't call Copyscape mid-pipeline.

```
Input → draft₀
Loop (≤4):
  Gemini "AI-likelihood proxy" call: returns {score 0-100, flagged_phrases[]}
  If score < 30 → break
  GPT paraphrase call with prompt: "Your previous draft scored X. Aggressively
    paraphrase, prioritizing lexical diversity and clause reordering, with
    extra attention to: <flagged_phrases>"
→ Final output
```

**Internal signal:** the AI-likelihood proxy. Never Copyscape.

### M4 — Burstiness Forcer

Attack the burstiness signal with a deterministic transform, no rewrite gymnastics.

```
Input → Gemini rewrite → Compute σ(sentence_lengths)
If σ < 7:
  Burstify (deterministic): merge ~30% of adjacent sentences into long winding ones,
    fragment ~30% into 3-6 word punchy ones
  Recompute σ; repeat until σ ≥ 8
Gemini light polish (preserve burstiness, fix grammar only)
→ Final output
```

**Internal signal:** deterministic σ — free, fast.
**Why it could work:** burstiness is a known dominant signal and a non-LLM fix is invisible to detectors trained on LLM distributions.

### M5 — N-Best Sampling + Stylometric Judge

Trade cost for variance.

```
Input → 5 parallel drafts:
  draft_1: Gemini @ temp 0.7, academic prompt
  draft_2: Gemini @ temp 0.9, conversational prompt
  draft_3: Gemini @ temp 1.1, journalist prompt
  draft_4: GPT-then-Gemini chain
  draft_5: Gemini-then-GPT chain
Score each with stylometric scorer (deterministic, free):
  combined_score = w1*sentence_σ_dist_from_human + w2*type_token_ratio
                 + w3*function_word_ratio + w4*punctuation_entropy
Return draft with lowest combined_score
```

**Internal signal:** deterministic stylometric scorer. Copyscape only sees the chosen winner.
**Cost note:** 5× draft cost. Allowed to exceed soft cap if it wins decisively.

### M6 — Sentence-Surgical Rewrite

Don't rewrite already-human sentences.

```
Input → Gemini rewrite (full draft)
Split draft into sentences
For each sentence: Gemini classifier prompt → score 0-10 ai-likelihood
Rewrite only the worst 30% (top-N by score):
  GPT targeted rewrite with sentence + surrounding context
Stitch sentences back together
Gemini light polish for transition consistency
→ Final output
```

**Why it could work:** surgical preservation. Rewriting everything blunts already-good sentences.

### M7 — Voice-Anchoring (Few-Shot Human Style)

Borrow a real human's stylometric fingerprint instead of describing one.

```
Anchor library (committed in repo): 3 short paragraphs of confirmed human academic writing
Input → Gemini rewrite with prompt:
  "Here are 3 examples of human academic prose. Mimic their cadence, sentence
   variance, word choice, and punctuation rhythm. Do not copy phrases.
   Now rewrite the following: <input>"
→ Perturb → GPT polish (with same anchor) → Final output
```

Test 2 anchor sets within this method (academic-formal vs academic-casual); pick best per-text.

### M8 — Combo: M1 + M2 + M4

The kitchen-sink candidate. Pipeline:

```
Input → Gemini rewrite
M4 burstify pass
M1 diagnostic-critic loop (≤2 iterations)
M2 self-critique pass (1 iteration)
GPT polish
→ Final output
```

**Why test it:** stacking might compound; or might interfere (later passes undoing earlier ones). Empirical question.

## Benchmark Corpus

5 fixed AI-written texts, generated once, committed to `master` at `backend/scripts/bench/corpus/`:

| ID | Words | Tone | Notes |
|----|-------|------|-------|
| T1 | ~100 | academic literature review | matches user's reported example |
| T2 | ~250 | technical explainer | medium length, neutral tone |
| T3 | ~400 | argumentative essay | long, formal, opinion |
| T4 | ~150 | conversational/blog | short, informal |
| T5 | ~500 | formal report | longest, dense |

Generation: a one-time Gemini call with prompt "Write a [tone] of ~N words about [topic]. Make it obvious AI output." Files committed as plain `.txt`.

## Harness

`backend/scripts/humanizer-bench.ts` — a CLI committed on `master` and inherited by every worktree.

```
Usage: ts-node backend/scripts/humanizer-bench.ts --method MX [--text T1|...|all] [--copyscape true]

Behavior:
  - Loads the named method's pipeline (registered in a method registry that worktrees
    extend).
  - Runs it on the named text(s) — default: all.
  - Prints one JSON line per (method, text):
      { method, text, score_in, score_out, tokens_in, tokens_out, duration_ms, output_text }
  - When --copyscape true, also calls Copyscape on score_in and score_out.
  - Writes consolidated results to bench-results/MX.json.
```

The method registry is keyed by string and lives at `backend/services/humanizer/methods/index.ts`. Each worktree adds its method file (`methods/MX_<name>.ts`) and registers it. v7 stays as `M0` for the baseline column.

## Judging Strategy (3-round elimination)

**Round 1 — Quick prune.** All 8 methods run T1, single Copyscape call each (8 calls).
- Drop any method with `score_out > 80` OR `(score_in - score_out) < 30`.

**Round 2 — Depth.** Survivors run T2–T5. ~4 × N_survivors calls.
- Compute mean / median / max per method.

**Round 3 — Tiebreak.** Top 2 finalists each re-run T2–T5 three times. ~24 calls.
- The lower-noise mean wins.

Worst case ~56 Copyscape calls; best case ~25.

## Orchestration

1. **Master prep (sequential).** On `master`:
   - Generate + commit `backend/scripts/bench/corpus/T{1..5}.txt`.
   - Build the method registry + harness CLI.
   - Register `M0` (current v7 pipeline) for baseline numbers.
   - Run `M0` on all 5 texts to establish baseline column.

2. **Worktree fan-out (parallel).** From `master` create 8 worktrees:
   - `experiment/humanizer-M1-diagnostic-critic`
   - `experiment/humanizer-M2-self-critique`
   - `experiment/humanizer-M3-adversarial-paraphrase`
   - `experiment/humanizer-M4-burstiness-forcer`
   - `experiment/humanizer-M5-n-best`
   - `experiment/humanizer-M6-sentence-surgical`
   - `experiment/humanizer-M7-voice-anchoring`
   - `experiment/humanizer-M8-combo`

   Spawn 8 parallel sub-agents via `dispatching-parallel-agents`. Each agent:
   - Implements its method file under `backend/services/humanizer/methods/MX_*.ts`
   - Registers it in the registry
   - Runs `humanizer-bench --method MX --text T1 --copyscape true` (Round 1)
   - Reports back with `{score_in, score_out, tokens, duration}` for T1

3. **Round 2 dispatch.** Aggregator (main session) reads round-1 reports, marks survivors, dispatches survivors to run T2–T5. Each survivor agent commits its `bench-results/MX.json` to its branch.

4. **Round 3 dispatch.** Top 2 finalists re-run T2–T5 three times.

5. **Selection + merge.** Aggregator builds a comparison table, picks winner (lowest mean score with cost ≤ ~Copyscape per-call price unless winning margin is overwhelming), merges that branch into `feat/humanize-crossmodel-perturbation` as v8, deprecates the v7 self-improvement loop.

## Acceptance Criteria

- All 5 corpus texts committed on `master`.
- Bench harness runs M0 successfully and prints baseline JSON.
- 8 method branches exist with per-method `bench-results/MX.json`.
- A `bench-results/comparison.md` aggregating all 8 methods + M0 baseline.
- Winner merged to `feat/humanize-crossmodel-perturbation`. End-to-end smoke test on the original 101-word text shows score < 50 (rough success threshold; actual bar set after seeing the bake-off distribution).

## Out of Scope

- Touching the AI-detector engine, the Copyscape provider, or the public humanize API surface.
- Frontend changes (only backend pipeline swaps).
- Replacing Copyscape with another judge (the user has stated Copyscape is the judge of record).
- Training models, RL fine-tuning (StealthRL-style). Inference-only methods only.

## Risks

- **Copyscape variance.** Same text scored twice may differ by ±5. Mitigation: round-3 averaging.
- **Method ties.** Two methods within Copyscape's noise floor. Mitigation: prefer the lower-cost / simpler one.
- **All methods fail.** If no method beats v7, we keep v7 and write up findings — the negative result is itself the deliverable for "owning the tech."
