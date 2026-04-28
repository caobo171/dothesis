# Humanizer v7: Cross-Model Chain + Programmatic Perturbation

**Status:** Approved design
**Branch:** `feat/humanize-crossmodel-perturbation`
**Date:** 2026-04-28

## Problem

The current humanizer pipeline (v6) fails GPTZero detection at 100% AI confidence even with aggressive prompt engineering. Symptoms:

- Internal statistical detector reports score 13-18 (passing) but GPTZero reports 100% AI
- All flagged sentences are highlighted yellow in GPTZero's "AI Sentences" view
- Iterating the pipeline doesn't help — the loop exits after iteration 1 because our scorer says we passed
- Our scorer is calibrated against statistical features (sentence length variance, vocabulary diversity, transition word density), but GPTZero 4.4b uses a neural classifier that measures token-level perplexity against a database of LLM outputs

**Root cause:** Any single LLM produces low-perplexity text — each token is the most probable continuation given the previous tokens. GPTZero's neural model is trained to recognize this property regardless of surface-level prompt instructions. No amount of prompt engineering can change the underlying token distribution that the model produces.

## Solution: Cross-Model Chain + Programmatic Perturbation

Two independent mechanisms, layered:

1. **Cross-model rewriting**: When Model B rewrites Model A's output, it "translates" the text into its own distribution, partially destroying Model A's fingerprint. Multiple cross-model passes mix distributions further.
2. **Programmatic perturbation**: Deterministic/random transformations applied between LLM passes. These don't come from any LLM, so GPTZero can't match them to a known model distribution. They raise per-token perplexity by injecting genuinely unpredictable choices.

Neither mechanism alone is enough. The combination is the breakthrough.

## Pipeline Architecture

```
Input
  │
  ▼
┌──────────────────────────┐
│ Stage 1: Gemini Rewrite  │  Creative restructuring (varied grammar, sensory language)
└──────────────────────────┘
  │
  ▼
┌──────────────────────────┐
│ Perturbation Layer 1     │  Synonym swap, contractions, markers, splits, punctuation
└──────────────────────────┘
  │
  ▼
┌──────────────────────────┐
│ Stage 2: GPT Cross-Rewrite│  Cross-model corruption — rewrites Gemini's perturbed output
└──────────────────────────┘
  │
  ▼
┌──────────────────────────┐
│ Perturbation Layer 2     │  Second pass of programmatic perturbations
└──────────────────────────┘
  │
  ▼
┌──────────────────────────┐
│ Stage 3: Gemini Polish   │  Light coherence pass at low temperature (0.3)
└──────────────────────────┘
  │
  ▼
Score (statistical detector — informational only, no iteration)
```

**Key changes from v6:**

- Linear pipeline, no iterative loop
- No critic stage (may be added back later if quality issues found)
- 3 LLM calls (same as v6: preprocess + critic + rewrite)
- 2 programmatic perturbation layers between LLM stages

**Why no iterative loop:** The previous loop exited on iteration 1 because our scorer reports passing scores even when GPTZero rejects. Without a reliable scorer that predicts GPTZero, iteration burns tokens without improving GPTZero pass rate. The score is still computed for telemetry but doesn't gate output.

**Why GPT for the middle stage:** GPTZero is trained primarily on GPT outputs, so GPT rewriting Gemini's output specifically targets the distribution GPTZero is most tuned to detect — by overwriting it with fresh GPT tokens that have already been perturbed. The resulting text has been through both distributions plus two perturbation layers.

## Perturbation Engine

The breakthrough piece. Six operations applied randomly to ~30-40% of sentences (rate scales with strength).

### Operations

| Operation | Description | Effect on GPTZero |
|---|---|---|
| **Synonym swap** | Replace common words with less-predictable alternatives from a built-in dictionary | Raises per-token perplexity — picks lower-probability words than any LLM would |
| **Contraction toggle** | "it is" ↔ "it's", "do not" ↔ "don't" | LLMs are inconsistent about contractions in formal text in ways humans aren't |
| **Human marker injection** | Insert "honestly", "look", "I mean", "actually" at random sentence starts | Filler words LLMs almost never produce naturally in academic writing |
| **Sentence splitting** | Split long sentences at commas into two shorter ones | Creates burstiness — sudden length changes between adjacent sentences |
| **Punctuation variation** | Replace periods with semicolons, add em dashes, ellipses | LLMs overwhelmingly default to periods and commas |
| **Starter variation** | Begin random sentences with "And", "But", "So", "Still" | Human writing habit; LLMs avoid these in formal text |

### Constraints

- Each sentence gets at most 2 perturbation operations to avoid unreadability
- Operations chosen randomly per sentence
- Perturbation rate scales with the existing user `strength` setting:
  - `strength ≤ 30` → 20% of sentences perturbed
  - `strength 31-70` → 35% of sentences perturbed
  - `strength > 70` → 50% of sentences perturbed

### Language awareness

The engine detects EN vs VI using the existing `detectLanguage()` from the statistical provider, then loads language-specific dictionaries:

- **English**: full set of 6 operations, English synonym dictionary, English human markers
- **Vietnamese**: 5 operations (no contraction toggle — Vietnamese has no contractions), Vietnamese synonym dictionary, Vietnamese human markers ("thực ra", "nói thật", etc.)

### Synonym dictionary scope

The built-in dictionary covers ~200 most common LLM-overused words per language, mapped to 2-4 less common alternatives each. Examples:

```typescript
en: {
  'important': ['key', 'central', 'big', 'real'],
  'demonstrate': ['show', 'prove', 'reveal', 'lay bare'],
  'utilize': ['use', 'rely on', 'lean on'],
  'significant': ['real', 'serious', 'big', 'meaningful'],
  // ... ~200 entries
}
```

Larger external dictionaries (Datamuse API, WordsAPI) are deliberately excluded for v7 to avoid external dependencies and rate limits. The built-in dictionary can be expanded over time based on observed GPTZero flag patterns.

## File Structure

```
backend/src/services/humanizer/
  ├── humanizer.service.ts           # Main pipeline (refactored)
  ├── perturbation/
  │   ├── perturbation.engine.ts     # Orchestrator — applies ops to text
  │   ├── synonym.dictionary.ts      # EN + VI synonym maps
  │   ├── human-markers.ts           # Filler word lists EN + VI
  │   └── operations.ts              # The 6 perturbation operation functions
  └── prompts/
      ├── rewrite.prompt.ts          # Stage 1: Gemini structured rewrite
      ├── cross-rewrite.prompt.ts    # Stage 2: GPT cross-model rewrite
      └── polish.prompt.ts           # Stage 3: Gemini final polish
```

The current `humanizer.service.ts` will be moved into the new `humanizer/` directory and refactored. Imports in routes and queues will be updated to the new path.

## Module Boundaries

### `PerturbationEngine`

**Purpose:** Apply programmatic perturbations to text without invoking any LLM.

**Public interface:**
```typescript
class PerturbationEngine {
  static perturb(text: string, strength: number): string
}
```

**Dependencies:** synonym dictionary, human markers list, language detection.

**Testable in isolation:** Yes — pure function, deterministic given a seed.

### Prompt builders

Three small, focused functions instead of one monolithic builder:

- `buildRewritePrompt(tone, strength, lengthMode)` → for Gemini stage 1
- `buildCrossRewritePrompt(tone)` → for GPT stage 2 (instructs GPT to rewrite the perturbed text while preserving the perturbations)
- `buildPolishPrompt()` → for Gemini stage 3 (light coherence pass, instructs to fix only awkwardness, preserve perturbations)

The cross-rewrite and polish prompts both explicitly tell the model to **preserve** the perturbations introduced by the perturbation engine — otherwise the model would "fix" the contractions, fillers, and split sentences back into smooth LLM-style text.

## API Contract

**Unchanged:**

- `POST /humanize/run` — SSE streaming
- `POST /humanize/run-sync` — JSON response
- `POST /humanize/check-score` — standalone score check
- All request/response shapes preserved

**Streaming events** — `stage` event payloads change to reflect new stages:

- `{ stage: 'rewriting', step: 'gemini_rewrite' }`
- `{ stage: 'perturbing', step: 'perturbation_1' }`
- `{ stage: 'rewriting', step: 'gpt_cross_rewrite' }`
- `{ stage: 'perturbing', step: 'perturbation_2' }`
- `{ stage: 'polishing', step: 'gemini_polish' }`
- `{ stage: 'score', score: <number> }` (terminal, informational)

The frontend doesn't render stage details by name (it just shows a progress indicator), so this change is non-breaking.

**Token usage** — `tokenUsage.steps` will have 3 entries instead of variable iterations:

```typescript
[
  { step: 'gemini_rewrite', model: 'gemini-3-flash-preview', ... },
  { step: 'gpt_cross_rewrite', model: 'gpt-5.5', ... },
  { step: 'gemini_polish', model: 'gemini-3-flash-preview', ... },
]
```

## Error Handling

- If any LLM stage fails, the pipeline aborts and the job is marked `failed` (same as current behavior).
- The perturbation engine is pure code — it cannot fail in normal operation. If it throws (e.g., malformed input), the pipeline aborts with the error.
- Empty text input is rejected at the route layer (existing behavior).

## Testing Strategy

**Unit tests:**

- Each perturbation operation tested in isolation with known input/output pairs
- `PerturbationEngine.perturb()` tested for: rate scaling with strength, language detection routing, max-2-ops-per-sentence constraint
- Synonym dictionary lookup tested for hit/miss cases

**Integration tests:**

- End-to-end pipeline run with a sample text, asserting all 5 stages execute in order
- Token usage shape assertion
- SSE event sequence assertion

**Manual GPTZero testing:**

- A scratch script (`backend/src/scripts/test-gptzero.ts`) that runs sample texts through the pipeline and prints output for manual paste into GPTZero. Not automated since we don't have the API.
- Test against the 4 existing sample texts (`/humanize/samples` endpoint) plus 2 Vietnamese samples.

## Rollout

- Implementation on `feat/humanize-crossmodel-perturbation` branch
- Manual GPTZero testing before merge — must show GPTZero confidence drop on at least 3 of the 4 English samples and 1 Vietnamese sample
- If quality regression observed (output reads awkwardly), tune perturbation rate down or refine the polish prompt before merge
- After merge, monitor `aiScoreOut` distribution in production for a week to spot regressions

## Out of Scope

- GPTZero API integration as an in-pipeline scorer (cost-prohibitive at $18/month subscription, plus per-call costs)
- Sentence-level multi-model processing (Approach B — too many API calls per request)
- Extract-Reconstruct hybrid (Approach C — too complex for v7, may revisit later)
- External synonym APIs (Datamuse, WordsAPI) — deliberately deferred to keep the engine self-contained
- Reintroducing the critic stage — may add back in v8 if the linear pipeline produces visibly worse text on edge cases
