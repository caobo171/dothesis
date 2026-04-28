# Humanizer v8 Method Bake-Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a benchmarked bake-off of 8 humanizer pipelines, judge each with Copyscape (judge-only — never inside any pipeline), pick the winner, and merge it as v8.

**Architecture:** Phase A lays a shared foundation on `master` (corpus, method registry, harness CLI, stylometric scorer, LLM critic). Phase B implements one method per git worktree in parallel; each is a self-contained file under `backend/src/services/humanizer/methods/`. Phase C runs the 3-round elimination judging and merges the winner.

**Tech Stack:** TypeScript, Node ts-node, existing `GeminiService` / `OpenAIService` / `AIDetectorEngine` (Copyscape provider), Vitest for unit tests, git worktrees + parallel agents for fan-out.

**Spec reference:** `docs/superpowers/specs/2026-04-28-humanizer-method-bakeoff-design.md`

---

## File Structure

Files this plan creates or modifies:

```
backend/src/services/humanizer/
├── methods/
│   ├── index.ts                     # Method registry (registerMethod, getMethod, listMethods)
│   ├── types.ts                     # HumanizerMethod, MethodResult, BenchRecord types
│   ├── M0_v7_baseline.ts            # Wraps current HumanizerService.humanizePipeline
│   ├── M1_diagnostic_critic.ts
│   ├── M2_self_critique.ts
│   ├── M3_adversarial_paraphrase.ts
│   ├── M4_burstiness_forcer.ts
│   ├── M5_n_best.ts
│   ├── M6_sentence_surgical.ts
│   ├── M7_voice_anchoring.ts
│   └── M8_combo.ts
├── critic/
│   ├── ai_likelihood_proxy.ts       # LLM AI-tell critic (used by M1, M3, M6, M8)
│   └── ai_likelihood_proxy.test.ts
├── stylometric/
│   ├── scorer.ts                    # Deterministic stylometric scorer (used by M5)
│   └── scorer.test.ts
└── burstify/
    ├── burstify.ts                  # Deterministic burstiness transform (used by M4, M8)
    └── burstify.test.ts

backend/scripts/bench/
├── humanizer-bench.ts               # CLI harness
├── corpus/
│   ├── T1.txt   ~100 words academic literature review
│   ├── T2.txt   ~250 words technical explainer
│   ├── T3.txt   ~400 words argumentative essay
│   ├── T4.txt   ~150 words conversational/blog
│   └── T5.txt   ~500 words formal report
└── anchors/
    ├── academic_formal.txt          # 3 paragraphs human academic prose (M7)
    └── academic_casual.txt

bench-results/
├── M0.json   ... M8.json            # Per-method results (one per worktree)
└── comparison.md                    # Final aggregated table (Phase C)
```

Each method file exports a single `run(input, opts) → MethodResult` function and self-registers in the registry on import. The harness imports the registry and dispatches by method id.

---

## Phase A — Foundation (sequential, on `master`)

### Task 1: Set up branch + directory scaffolding

**Files:**
- Create: `backend/src/services/humanizer/methods/` (empty dir)
- Create: `backend/src/services/humanizer/critic/` (empty dir)
- Create: `backend/src/services/humanizer/stylometric/` (empty dir)
- Create: `backend/src/services/humanizer/burstify/` (empty dir)
- Create: `backend/scripts/bench/corpus/` (empty dir)
- Create: `backend/scripts/bench/anchors/` (empty dir)
- Create: `bench-results/` (empty dir)

- [ ] **Step 1: Create new branch off `feat/humanize-crossmodel-perturbation`**

```bash
cd /Users/caonguyenvan/project/dothesis
git checkout feat/humanize-crossmodel-perturbation
git pull
git checkout -b feat/humanizer-v8-bakeoff
```

- [ ] **Step 2: Create directories with .gitkeep files**

```bash
mkdir -p backend/src/services/humanizer/methods
mkdir -p backend/src/services/humanizer/critic
mkdir -p backend/src/services/humanizer/stylometric
mkdir -p backend/src/services/humanizer/burstify
mkdir -p backend/scripts/bench/corpus
mkdir -p backend/scripts/bench/anchors
mkdir -p bench-results
touch backend/src/services/humanizer/methods/.gitkeep
touch backend/src/services/humanizer/critic/.gitkeep
touch backend/src/services/humanizer/stylometric/.gitkeep
touch backend/src/services/humanizer/burstify/.gitkeep
touch backend/scripts/bench/corpus/.gitkeep
touch backend/scripts/bench/anchors/.gitkeep
touch bench-results/.gitkeep
```

- [ ] **Step 3: Commit scaffolding**

```bash
git add backend/src/services/humanizer/methods backend/src/services/humanizer/critic backend/src/services/humanizer/stylometric backend/src/services/humanizer/burstify backend/scripts/bench bench-results
git commit -m "scaffold(humanizer): directories for v8 method bake-off"
```

---

### Task 2: Define method registry + shared types

**Files:**
- Create: `backend/src/services/humanizer/methods/types.ts`
- Create: `backend/src/services/humanizer/methods/index.ts`

- [ ] **Step 1: Write `types.ts`**

```ts
// backend/src/services/humanizer/methods/types.ts

// Shared shape for every humanizer method in the bake-off. Keeping methods
// behind a uniform interface lets the bench harness dispatch by id without
// caring about each method's internal pipeline.

export type MethodOptions = {
  tone: string;        // 'academic' | 'casual' | etc, mirrors HumanizerService
  strength: number;    // 0-100, mirrors HumanizerService
  lengthMode: string;  // 'match' | 'shorter' | 'longer'
};

export type MethodTokenStep = {
  step: string;        // free-form label, e.g. 'gemini_critic', 'gpt_paraphrase'
  model: string;
  inputTokens: number;
  outputTokens: number;
};

export type MethodResult = {
  output: string;
  tokenSteps: MethodTokenStep[];
};

export type HumanizerMethod = {
  id: string;          // 'M0' | 'M1' | ... | 'M8'
  description: string; // short human label
  run(input: string, opts: MethodOptions): Promise<MethodResult>;
};

// One row per (method, text) in the bench output JSON.
export type BenchRecord = {
  methodId: string;
  textId: string;
  scoreIn: number | null;       // Copyscape score on input, null if --copyscape false
  scoreOut: number | null;
  tokenSteps: MethodTokenStep[];
  totalInputTokens: number;
  totalOutputTokens: number;
  durationMs: number;
  output: string;
};
```

- [ ] **Step 2: Write `index.ts` registry**

```ts
// backend/src/services/humanizer/methods/index.ts

// Decision: Keep the registry as a plain Map keyed by method id, populated
// via side-effect imports. Each method file calls registerMethod() at module
// top level. The harness imports './methods' to load every registered method.

import type { HumanizerMethod } from './types';

const registry = new Map<string, HumanizerMethod>();

export function registerMethod(m: HumanizerMethod): void {
  if (registry.has(m.id)) {
    throw new Error(`Method ${m.id} already registered`);
  }
  registry.set(m.id, m);
}

export function getMethod(id: string): HumanizerMethod {
  const m = registry.get(id);
  if (!m) throw new Error(`No method registered with id ${id}. Known: ${[...registry.keys()].join(',')}`);
  return m;
}

export function listMethods(): HumanizerMethod[] {
  return [...registry.values()].sort((a, b) => a.id.localeCompare(b.id));
}

// Side-effect imports register the methods. Add new methods here as they land.
import './M0_v7_baseline';
// M1-M8 imports are added in their respective worktrees.

export type { HumanizerMethod, MethodOptions, MethodResult, BenchRecord, MethodTokenStep } from './types';
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/methods
git commit -m "feat(humanizer): method registry + shared types"
```

---

### Task 3: Wrap current v7 pipeline as M0 baseline

**Files:**
- Create: `backend/src/services/humanizer/methods/M0_v7_baseline.ts`

- [ ] **Step 1: Write `M0_v7_baseline.ts`**

```ts
// backend/src/services/humanizer/methods/M0_v7_baseline.ts

// M0 = current v7 pipeline (cross-model + perturbation + self-improvement loop).
// Acts as the baseline column in the bake-off. We wrap HumanizerService.humanizePipeline
// rather than copy its body so M0 stays in lockstep with whatever ships as v7 today.

import { HumanizerService } from '../humanizer.service';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const result = await HumanizerService.humanizePipeline(input, opts.tone, opts.strength, opts.lengthMode);
  return {
    output: result.rewrittenText,
    tokenSteps: result.tokenUsage.steps.map(s => ({
      step: s.step,
      model: s.model,
      inputTokens: s.inputTokens,
      outputTokens: s.outputTokens,
    })),
  };
}

registerMethod({
  id: 'M0',
  description: 'v7 baseline: cross-model + perturbation + self-improvement loop',
  run,
});
```

- [ ] **Step 2: Verify TS compiles**

```bash
cd backend
npx tsc --noEmit
```
Expected: no errors related to the new files.

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/methods/M0_v7_baseline.ts
git commit -m "feat(humanizer): register M0 baseline wrapping v7 pipeline"
```

---

### Task 4: Stylometric scorer utility

**Files:**
- Create: `backend/src/services/humanizer/stylometric/scorer.ts`
- Test: `backend/src/services/humanizer/stylometric/scorer.test.ts`

This is the deterministic feature scorer M5 uses to pick the best of N drafts. Lower score = more human-like.

- [ ] **Step 1: Write the failing test**

```ts
// backend/src/services/humanizer/stylometric/scorer.test.ts
import { describe, it, expect } from 'vitest';
import { stylometricScore, sentenceLengthSigma } from './scorer';

describe('stylometricScore', () => {
  it('returns lower score for high-burstiness text than for uniform text', () => {
    const uniform = 'This is a sentence of medium length here. ' +
                    'This is another sentence of medium length too. ' +
                    'This is yet another sentence of medium length here.';
    const bursty = 'Short. ' +
                   'A medium sentence sits in the middle. ' +
                   'Then a long, winding, comma-laden sentence rambles on with multiple clauses, ' +
                   'asides, and changes of direction before finally arriving at its end. ' +
                   'Tiny.';
    expect(stylometricScore(bursty)).toBeLessThan(stylometricScore(uniform));
  });

  it('sentenceLengthSigma is 0 for single sentence', () => {
    expect(sentenceLengthSigma('Just one sentence.')).toBe(0);
  });

  it('sentenceLengthSigma > 5 for highly varied text', () => {
    const text = 'Hi. ' +
                 'A medium one here. ' +
                 'Now a much longer sentence that runs on quite a bit and includes several thoughts.';
    expect(sentenceLengthSigma(text)).toBeGreaterThan(5);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
npx vitest run src/services/humanizer/stylometric/scorer.test.ts
```
Expected: FAIL — `stylometricScore` and `sentenceLengthSigma` not defined.

- [ ] **Step 3: Implement scorer**

```ts
// backend/src/services/humanizer/stylometric/scorer.ts

// Deterministic stylometric scorer used by M5 to rank candidate drafts.
// All four sub-features are normalized so each contributes ~equally to the
// final score. Lower score = more human-like (higher burstiness, higher
// vocabulary diversity, function-word ratio in human range, varied
// punctuation).

const HUMAN_FUNCTION_WORD_RATIO = 0.45; // empirical mid-range for English prose
const FUNCTION_WORDS = new Set([
  'the','a','an','and','or','but','if','then','of','in','on','at','to','for',
  'with','from','by','as','is','are','was','were','be','been','being','have',
  'has','had','do','does','did','will','would','could','should','can','may',
  'might','this','that','these','those','i','you','he','she','it','we','they',
  'me','him','her','us','them','my','your','his','its','our','their','not',
]);

function tokens(text: string): string[] {
  return (text.toLowerCase().match(/\b[a-z']+\b/g) || []);
}

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

export function sentenceLengthSigma(text: string): number {
  const lens = splitSentences(text).map(s => tokens(s).length);
  if (lens.length < 2) return 0;
  const mean = lens.reduce((a, b) => a + b, 0) / lens.length;
  const variance = lens.reduce((a, b) => a + (b - mean) ** 2, 0) / lens.length;
  return Math.sqrt(variance);
}

function typeTokenRatio(text: string): number {
  const t = tokens(text);
  if (t.length === 0) return 0;
  return new Set(t).size / t.length;
}

function functionWordRatio(text: string): number {
  const t = tokens(text);
  if (t.length === 0) return 0;
  const fw = t.filter(w => FUNCTION_WORDS.has(w)).length;
  return fw / t.length;
}

function punctuationEntropy(text: string): number {
  // Shannon entropy over the distribution of punctuation marks. Higher = more
  // varied punctuation rhythm; humans use a wider mix than AI.
  const puncts = (text.match(/[.,;:!?\-—()"]/g) || []);
  if (puncts.length === 0) return 0;
  const counts = new Map<string, number>();
  for (const p of puncts) counts.set(p, (counts.get(p) || 0) + 1);
  const total = puncts.length;
  let h = 0;
  for (const c of counts.values()) {
    const p = c / total;
    h -= p * Math.log2(p);
  }
  return h;
}

// Combined score: lower is more human-like.
// - burstiness: penalize σ < 7 (AI range), reward σ ∈ [7, 14]
// - typeTokenRatio: reward higher (more varied vocab)
// - functionWordRatio: penalize distance from HUMAN_FUNCTION_WORD_RATIO
// - punctuationEntropy: reward higher
export function stylometricScore(text: string): number {
  const sigma = sentenceLengthSigma(text);
  const ttr = typeTokenRatio(text);
  const fwr = functionWordRatio(text);
  const pe = punctuationEntropy(text);

  const burstinessPenalty = Math.max(0, 7 - sigma) * 5;        // 0 if σ ≥ 7, up to 35
  const ttrPenalty = Math.max(0, 0.5 - ttr) * 50;              // 0 if ttr ≥ 0.5
  const fwrPenalty = Math.abs(fwr - HUMAN_FUNCTION_WORD_RATIO) * 50;
  const punctPenalty = Math.max(0, 2.0 - pe) * 5;              // 0 if entropy ≥ 2 bits

  return burstinessPenalty + ttrPenalty + fwrPenalty + punctPenalty;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
npx vitest run src/services/humanizer/stylometric/scorer.test.ts
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/humanizer/stylometric
git commit -m "feat(humanizer): deterministic stylometric scorer for M5 + tests"
```

---

### Task 5: AI-likelihood proxy critic (LLM)

**Files:**
- Create: `backend/src/services/humanizer/critic/ai_likelihood_proxy.ts`
- Test: `backend/src/services/humanizer/critic/ai_likelihood_proxy.test.ts`

The Gemini-based critic that returns `{ score: 0-100, flagged: [{sentence, why}] }`. Used by M1, M3, M6, M8 — never calls Copyscape.

- [ ] **Step 1: Write the failing test (mock Gemini)**

```ts
// backend/src/services/humanizer/critic/ai_likelihood_proxy.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as ai from '../../ai/gemini.service';
import { aiLikelihoodProxy, parseProxyResponse } from './ai_likelihood_proxy';

describe('parseProxyResponse', () => {
  it('parses a clean JSON response', () => {
    const raw = '{"score":72,"flagged":[{"sentence":"foo","why":"bar"}]}';
    expect(parseProxyResponse(raw)).toEqual({
      score: 72,
      flagged: [{ sentence: 'foo', why: 'bar' }],
    });
  });

  it('strips markdown code fences before parsing', () => {
    const raw = '```json\n{"score":50,"flagged":[]}\n```';
    expect(parseProxyResponse(raw)).toEqual({ score: 50, flagged: [] });
  });

  it('returns score=100 and empty flagged on parse failure', () => {
    expect(parseProxyResponse('not json at all')).toEqual({ score: 100, flagged: [] });
  });
});

describe('aiLikelihoodProxy', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('calls Gemini and returns parsed result', async () => {
    vi.spyOn(ai.GeminiService, 'chat').mockResolvedValue({
      text: '{"score":42,"flagged":[{"sentence":"x","why":"y"}]}',
      usage: { inputTokens: 100, outputTokens: 50 },
    });
    const out = await aiLikelihoodProxy('some text');
    expect(out.score).toBe(42);
    expect(out.flagged).toHaveLength(1);
    expect(out.usage.inputTokens).toBe(100);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
npx vitest run src/services/humanizer/critic/ai_likelihood_proxy.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the critic**

```ts
// backend/src/services/humanizer/critic/ai_likelihood_proxy.ts

// LLM-based AI-likelihood proxy. Replaces Copyscape inside the pipeline so
// methods M1, M3, M6, M8 can iterate without making external scoring calls.
// Returns a 0-100 score (higher = more AI-like) and a list of specific
// flagged sentences with reasons. The pipeline uses both: the score gates
// the loop (stop iterating once score < threshold), the flagged list tells
// the next rewrite where to focus.

import { GeminiService } from '../../ai/gemini.service';

const SYSTEM_PROMPT = `You are an AI-text-detection diagnostic. Read the user's text and judge how AI-generated it sounds based on three signals:

1. PERPLEXITY: predictable / generic word choice (e.g. "utilize", "facilitate", "delve into")
2. BURSTINESS: uniform sentence length and rhythm
3. STYLOMETRIC TELLS: parallel structures, formal connectors ("Furthermore", "Moreover"), low function-word variety, sterile punctuation

Output strict JSON with this exact shape — no prose, no markdown:
{
  "score": <0-100, where 0=clearly human, 100=clearly AI>,
  "flagged": [
    { "sentence": "<exact substring of the input>", "why": "<short reason citing one of the signals>" }
  ]
}

Flag at most 5 sentences, the worst offenders. If the text is clearly human, return score < 30 and an empty flagged array.`;

export type ProxyFlag = { sentence: string; why: string };
export type ProxyResult = {
  score: number;
  flagged: ProxyFlag[];
  usage: { inputTokens: number; outputTokens: number };
};

export function parseProxyResponse(raw: string): { score: number; flagged: ProxyFlag[] } {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return {
      score: typeof parsed.score === 'number' ? parsed.score : 100,
      flagged: Array.isArray(parsed.flagged) ? parsed.flagged : [],
    };
  } catch {
    return { score: 100, flagged: [] };
  }
}

export async function aiLikelihoodProxy(text: string): Promise<ProxyResult> {
  const response = await GeminiService.chat(SYSTEM_PROMPT, text, {
    temperature: 0.1,
    maxTokens: 1024,
    jsonMode: true,
  });
  const { score, flagged } = parseProxyResponse(response.text);
  return {
    score,
    flagged,
    usage: response.usage,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
npx vitest run src/services/humanizer/critic/ai_likelihood_proxy.test.ts
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/humanizer/critic
git commit -m "feat(humanizer): AI-likelihood proxy critic (LLM-based, no Copyscape)"
```

---

### Task 6: Burstify deterministic transform

**Files:**
- Create: `backend/src/services/humanizer/burstify/burstify.ts`
- Test: `backend/src/services/humanizer/burstify/burstify.test.ts`

Used by M4 and M8. Pure deterministic transform on sentence boundaries.

- [ ] **Step 1: Write the failing test**

```ts
// backend/src/services/humanizer/burstify/burstify.test.ts
import { describe, it, expect } from 'vitest';
import { burstify } from './burstify';
import { sentenceLengthSigma } from '../stylometric/scorer';

describe('burstify', () => {
  it('increases sentence-length variance on uniform input', () => {
    const uniform = 'The system processes data through multiple stages effectively. ' +
                    'Each component handles its specific task with precision and care. ' +
                    'The output is then validated against expected results carefully. ' +
                    'Errors are logged and reported to the operator immediately. ' +
                    'This approach ensures reliability across all operating conditions.';
    const sigmaBefore = sentenceLengthSigma(uniform);
    const out = burstify(uniform, { seed: 1 });
    const sigmaAfter = sentenceLengthSigma(out);
    expect(sigmaAfter).toBeGreaterThan(sigmaBefore);
  });

  it('is deterministic given a seed', () => {
    const text = 'One. Two three. Four five six. Seven eight nine ten.';
    expect(burstify(text, { seed: 42 })).toBe(burstify(text, { seed: 42 }));
  });

  it('preserves total word count within ±10%', () => {
    const text = 'The cat sat on the mat. ' +
                 'The dog watched from afar. ' +
                 'A bird flew above the trees. ' +
                 'The wind blew through the leaves quietly.';
    const before = text.split(/\s+/).length;
    const after = burstify(text, { seed: 7 }).split(/\s+/).length;
    expect(after).toBeGreaterThanOrEqual(Math.floor(before * 0.9));
    expect(after).toBeLessThanOrEqual(Math.ceil(before * 1.1));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
npx vitest run src/services/humanizer/burstify/burstify.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement burstify**

```ts
// backend/src/services/humanizer/burstify/burstify.ts

// Deterministic transform that widens sentence-length variance. Targets the
// burstiness signal directly: detectors trained on LLM output expect uniform
// 12-18 word sentences, so we build outliers in both directions.
//
// Strategy: for each pair of adjacent sentences, with seeded probability
//   - merge them with a connector ("and", ";", "—")
//   - or fragment the longer one by clause split
// Roughly 30% of pairs touched, balanced merges and splits.

type Opts = { seed?: number };

function mulberry32(seed: number) {
  return function() {
    let t = seed += 0x6D2B79F5;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

function stripTrailingPunct(s: string): { body: string; punct: string } {
  const m = s.match(/^(.*?)([.!?]+)$/);
  if (!m) return { body: s, punct: '.' };
  return { body: m[1].trim(), punct: m[2] };
}

function fragmentSentence(s: string, rng: () => number): string[] {
  // Try to split on a comma into two pieces; only split if both pieces have ≥3 words.
  const { body, punct } = stripTrailingPunct(s);
  const commaIdx = body.indexOf(', ');
  if (commaIdx < 0) return [s];
  const left = body.slice(0, commaIdx).trim();
  const right = body.slice(commaIdx + 2).trim();
  if (left.split(/\s+/).length < 3 || right.split(/\s+/).length < 3) return [s];
  // Capitalize the right side's first letter.
  const rightCap = right.charAt(0).toUpperCase() + right.slice(1);
  return [`${left}.`, `${rightCap}${punct}`];
}

function mergeSentences(a: string, b: string, rng: () => number): string {
  const { body: aBody } = stripTrailingPunct(a);
  const { body: bBody, punct: bPunct } = stripTrailingPunct(b);
  // Lowercase b's first letter so the merged sentence reads cleanly.
  const bLower = bBody.charAt(0).toLowerCase() + bBody.slice(1);
  const connectors = [', and ', '; ', ' — '];
  const c = connectors[Math.floor(rng() * connectors.length)];
  return `${aBody}${c}${bLower}${bPunct}`;
}

export function burstify(text: string, opts: Opts = {}): string {
  const rng = mulberry32(opts.seed ?? 1);
  const sentences = splitSentences(text);
  if (sentences.length < 2) return text;

  const out: string[] = [];
  let i = 0;
  while (i < sentences.length) {
    const cur = sentences[i];
    const next = sentences[i + 1];
    const r = rng();
    if (next && r < 0.30) {
      // Merge with neighbor
      out.push(mergeSentences(cur, next, rng));
      i += 2;
    } else if (cur.split(/\s+/).length > 12 && r < 0.60) {
      // Fragment a longer sentence
      out.push(...fragmentSentence(cur, rng));
      i += 1;
    } else {
      out.push(cur);
      i += 1;
    }
  }
  return out.join(' ');
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
npx vitest run src/services/humanizer/burstify/burstify.test.ts
```
Expected: PASS (3 tests). If burstiness test is flaky on the chosen seed, adjust seed in the test until reliably increasing.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/humanizer/burstify
git commit -m "feat(humanizer): deterministic burstify transform for M4/M8"
```

---

### Task 7: Bench harness CLI

**Files:**
- Create: `backend/scripts/bench/humanizer-bench.ts`

- [ ] **Step 1: Write the harness**

```ts
// backend/scripts/bench/humanizer-bench.ts

// CLI: benchmark a humanizer method against the fixed corpus.
//
// Usage:
//   ts-node backend/scripts/bench/humanizer-bench.ts \
//     --method M3 \
//     --text T1                 # or 'all'
//     --copyscape true|false    # default true
//     --out bench-results/M3.json
//
// Behavior:
//   - Loads the requested method from the registry (which auto-imports all known methods).
//   - Reads corpus texts from backend/scripts/bench/corpus/<id>.txt.
//   - Runs the method on each, captures tokens + duration.
//   - When --copyscape true, calls AIDetectorEngine.detect on input and output.
//   - Appends one BenchRecord per (method, text) to the output JSON file.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { getMethod } from '../../src/services/humanizer/methods';
import { AIDetectorEngine } from '../../src/services/ai-detector';
import type { BenchRecord, MethodOptions } from '../../src/services/humanizer/methods/types';

type Args = {
  method: string;
  text: string;        // 'T1' | ... | 'T5' | 'all'
  copyscape: boolean;
  out: string;
};

function parseArgs(): Args {
  const argv = process.argv.slice(2);
  const get = (flag: string, def?: string) => {
    const i = argv.indexOf(flag);
    if (i < 0) return def;
    return argv[i + 1];
  };
  const method = get('--method');
  if (!method) throw new Error('--method required');
  return {
    method,
    text: get('--text', 'all')!,
    copyscape: (get('--copyscape', 'true')!) === 'true',
    out: get('--out', `bench-results/${method}.json`)!,
  };
}

const TEXT_IDS = ['T1', 'T2', 'T3', 'T4', 'T5'];
const CORPUS_DIR = path.resolve(__dirname, 'corpus');

function loadText(id: string): string {
  const p = path.join(CORPUS_DIR, `${id}.txt`);
  return fs.readFileSync(p, 'utf8').trim();
}

async function scoreCopyscape(text: string): Promise<number | null> {
  try {
    const r = await AIDetectorEngine.detect(text);
    return r.score;
  } catch (e) {
    console.error('[bench] Copyscape error:', (e as Error).message);
    return null;
  }
}

async function main() {
  const args = parseArgs();
  const method = getMethod(args.method);
  const ids = args.text === 'all' ? TEXT_IDS : [args.text];
  const opts: MethodOptions = { tone: 'academic', strength: 50, lengthMode: 'match' };

  const existing: BenchRecord[] = fs.existsSync(args.out)
    ? JSON.parse(fs.readFileSync(args.out, 'utf8'))
    : [];

  for (const textId of ids) {
    const input = loadText(textId);
    console.log(`[bench] ${method.id} on ${textId} (${input.split(/\s+/).length} words)`);

    const scoreIn = args.copyscape ? await scoreCopyscape(input) : null;

    const t0 = Date.now();
    const result = await method.run(input, opts);
    const durationMs = Date.now() - t0;

    const scoreOut = args.copyscape ? await scoreCopyscape(result.output) : null;

    const totalInputTokens = result.tokenSteps.reduce((s, x) => s + x.inputTokens, 0);
    const totalOutputTokens = result.tokenSteps.reduce((s, x) => s + x.outputTokens, 0);

    const record: BenchRecord = {
      methodId: method.id,
      textId,
      scoreIn,
      scoreOut,
      tokenSteps: result.tokenSteps,
      totalInputTokens,
      totalOutputTokens,
      durationMs,
      output: result.output,
    };

    console.log(`[bench] ${method.id}/${textId}: score ${scoreIn} → ${scoreOut} | tokens ${totalInputTokens}→${totalOutputTokens} | ${durationMs}ms`);
    existing.push(record);
  }

  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, JSON.stringify(existing, null, 2));
  console.log(`[bench] wrote ${existing.length} records to ${args.out}`);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 2: Verify TS compiles**

```bash
cd backend
npx tsc --noEmit -p tsconfig.json
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/bench/humanizer-bench.ts
git commit -m "feat(humanizer): bench harness CLI"
```

---

### Task 8: Generate corpus + anchor library

**Files:**
- Create: `backend/scripts/bench/corpus/T{1..5}.txt`
- Create: `backend/scripts/bench/anchors/academic_formal.txt`
- Create: `backend/scripts/bench/anchors/academic_casual.txt`

- [ ] **Step 1: Generate the 5 corpus texts**

Run a single Gemini call (manually, via the project's existing API client or any LLM playground) with this prompt for each text:

```
Write a [TONE] passage of approximately [N] words about [TOPIC].
Make it sound clearly machine-generated: use formal connectors ("Furthermore",
"Moreover", "Additionally"), uniform sentence length, generic word choices
("utilize", "facilitate", "leverage"), and parallel structures. Output ONLY
the passage, no preamble.
```

Texts to generate:
- **T1**: tone=academic literature review, N=100, topic="recent advances in transformer attention mechanisms"
- **T2**: tone=technical explainer, N=250, topic="how vector databases enable semantic search"
- **T3**: tone=argumentative essay, N=400, topic="why universal basic income would harm productivity"
- **T4**: tone=conversational blog, N=150, topic="my experience starting a morning routine"
- **T5**: tone=formal report, N=500, topic="Q1 2026 outlook for the global lithium market"

Save each output as plain text in `backend/scripts/bench/corpus/T{1..5}.txt`. Verify each file's word count is within ±20% of target.

- [ ] **Step 2: Write the two anchor files (M7 voice-anchoring)**

For each anchor, copy 3 short paragraphs (~80-120 words each) of clearly human academic prose. Sources can be a personal blog, an arxiv preprint's intro, a published essay — anything human-authored and academic in flavor. **Important: pick text that is unambiguously human (the author would not have used an LLM).**

- `backend/scripts/bench/anchors/academic_formal.txt` — 3 paragraphs, formal register
- `backend/scripts/bench/anchors/academic_casual.txt` — 3 paragraphs, looser register, first-person OK

- [ ] **Step 3: Sanity-check word counts**

```bash
cd /Users/caonguyenvan/project/dothesis
wc -w backend/scripts/bench/corpus/*.txt backend/scripts/bench/anchors/*.txt
```
Expected: T1 ≈ 100, T2 ≈ 250, T3 ≈ 400, T4 ≈ 150, T5 ≈ 500. Anchors ≈ 240-360 each.

- [ ] **Step 4: Commit corpus + anchors**

```bash
git add backend/scripts/bench/corpus backend/scripts/bench/anchors
git commit -m "feat(humanizer): bench corpus (5 texts) + voice anchors (2 sets)"
```

---

### Task 9: Run M0 baseline benchmark

**Files:**
- Create: `bench-results/M0.json`

- [ ] **Step 1: Run harness against M0 on all 5 texts with Copyscape on**

```bash
cd /Users/caonguyenvan/project/dothesis
cd backend && npx ts-node scripts/bench/humanizer-bench.ts --method M0 --text all --copyscape true --out ../bench-results/M0.json
```
Expected: ~5-15 minutes runtime; final line `wrote 5 records to ../bench-results/M0.json`. If Copyscape fails on any, the record stores `scoreOut: null` and the run continues.

- [ ] **Step 2: Inspect baseline numbers**

```bash
cd /Users/caonguyenvan/project/dothesis
cat bench-results/M0.json | jq '.[] | {textId, scoreIn, scoreOut, totalInputTokens, totalOutputTokens, durationMs}'
```
Expected: a JSON object per text with the four metrics. Eyeball the `scoreOut` column — this is the bar every other method must beat.

- [ ] **Step 3: Commit baseline results**

```bash
git add bench-results/M0.json
git commit -m "bench(humanizer): M0 baseline results on 5-text corpus"
```

- [ ] **Step 4: Push the foundation branch so worktrees can branch from it**

```bash
git push -u origin feat/humanizer-v8-bakeoff
```

---

## Phase B — Implement 8 methods (parallelizable across worktrees)

Each method follows the same template:
1. Create a worktree off `feat/humanizer-v8-bakeoff`.
2. Implement `methods/MX_*.ts` per the spec section for that method.
3. Add a side-effect import line to `methods/index.ts`.
4. (Optional) write a small unit test if non-trivial logic exists outside the LLM call.
5. Run `humanizer-bench --method MX --text T1 --copyscape true` (Round 1 single-text run).
6. Commit `bench-results/MX.json`.

These tasks can be dispatched in parallel via `dispatching-parallel-agents` since the worktrees are independent.

> **Spec contract:** every method file MUST end with `registerMethod({ id: 'MX', description: '...', run })` so the harness can find it.

### Task 10: Implement M1 — Diagnostic Critic

**Worktree:** `experiment/humanizer-M1-diagnostic-critic`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M1 -b experiment/humanizer-M1-diagnostic-critic feat/humanizer-v8-bakeoff
cd ../dothesis-M1
```

- [ ] **Step 2: Write `methods/M1_diagnostic_critic.ts`**

```ts
// backend/src/services/humanizer/methods/M1_diagnostic_critic.ts

// M1: Diagnostic Critic. Replaces v7's blind self-improvement loop with a
// targeted critic-then-rewrite loop. The critic identifies up to 5 sentences
// that still sound AI-generated; the rewriter rewrites only those sentences
// with the reasons attached. Loops up to 3 times or until the critic returns
// an empty flagged list.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { PerturbationEngine } from '../perturbation/perturbation.engine';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 3;
const PROXY_TARGET_SCORE = 30;

const TARGETED_REWRITE_PROMPT = `You are a careful editor. The user supplies:
1. A FULL_TEXT passage.
2. A FLAGGED list of (sentence, reason) — these specific sentences still sound AI-generated.

Rewrite ONLY the flagged sentences, addressing the stated reasons (e.g. if the
reason is "uniform sentence length", make this one noticeably shorter or longer
than its neighbors; if "generic verb choice", swap for an unexpected but
appropriate word; if "parallel structure", break the parallelism). Return the
FULL_TEXT with only the flagged sentences rewritten in place. Output strict JSON:
{ "rewrittenText": "<full text>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Stage 1: initial Gemini rewrite (re-use existing v7 prompt)
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  // Stage 2: cross-model perturb + GPT rewrite (matches v7 flavor)
  draft = PerturbationEngine.perturb(draft, opts.strength);
  const stage2 = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  draft = parseRewritten(stage2.text) || draft;
  tokens.push({ step: 'gpt_cross_rewrite', model: 'gpt-5.5', inputTokens: stage2.usage.inputTokens, outputTokens: stage2.usage.outputTokens });

  // Diagnostic-critic loop
  for (let i = 0; i < MAX_LOOPS; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `critic_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < PROXY_TARGET_SCORE || proxy.flagged.length === 0) break;

    const flaggedJson = JSON.stringify(proxy.flagged);
    const userMsg = `FULL_TEXT:\n${draft}\n\nFLAGGED:\n${flaggedJson}`;
    const fix = await GeminiService.chat(TARGETED_REWRITE_PROMPT, userMsg, {
      temperature: 0.7, maxTokens: 4096, jsonMode: true,
    });
    draft = parseRewritten(fix.text) || draft;
    tokens.push({ step: `targeted_rewrite_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: fix.usage.inputTokens, outputTokens: fix.usage.outputTokens });
  }

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim()
      ? parsed.rewrittenText
      : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M1', description: 'Diagnostic critic: LLM AI-tell critic guides targeted rewrites', run });
```

- [ ] **Step 3: Add side-effect import to registry**

In `backend/src/services/humanizer/methods/index.ts`, after `import './M0_v7_baseline';` add:

```ts
import './M1_diagnostic_critic';
```

- [ ] **Step 4: TS check**

```bash
cd backend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Round-1 benchmark on T1 with Copyscape**

```bash
cd /Users/caonguyenvan/project/dothesis-M1/backend
npx ts-node scripts/bench/humanizer-bench.ts --method M1 --text T1 --copyscape true --out ../bench-results/M1.json
```
Expected: writes 1 record to `bench-results/M1.json`. Inspect `scoreOut`.

- [ ] **Step 6: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis-M1
git add backend/src/services/humanizer/methods backend/src/services/humanizer/critic backend/src/services/humanizer/stylometric backend/src/services/humanizer/burstify bench-results/M1.json
git commit -m "feat(humanizer): M1 diagnostic critic + round-1 T1 result"
git push -u origin experiment/humanizer-M1-diagnostic-critic
```

---

### Task 11: Implement M2 — Self-Critique Loop

**Worktree:** `experiment/humanizer-M2-self-critique`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M2 -b experiment/humanizer-M2-self-critique feat/humanizer-v8-bakeoff
cd ../dothesis-M2
```

- [ ] **Step 2: Write `methods/M2_self_critique.ts`**

```ts
// backend/src/services/humanizer/methods/M2_self_critique.ts

// M2: Self-Critique. Same shape as M1 but the rewriter critiques its own
// previous draft (no separate critic). The model is asked first to identify
// 3-5 sentences in *its own output* that still sound AI, then to rewrite
// against that self-assessment. Repeat ≤3 times.

import { GeminiService } from '../../ai/gemini.service';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 3;

const SELF_CRITIQUE_PROMPT = `You wrote the passage below in a previous turn. Now look at it with fresh eyes
and identify 3-5 sentences that still sound AI-generated. Reasons may include:
generic word choice, uniform sentence length, parallel structure, formal connectors,
sterile punctuation. Then rewrite the WHOLE passage, fixing those specific
issues — make some sentences much shorter, others longer with multiple clauses,
swap predictable verbs for unexpected ones. Output strict JSON:
{ "critique": ["<bullet>", "..."], "rewrittenText": "<full revised passage>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  // Self-critique iterations
  for (let i = 0; i < MAX_LOOPS; i++) {
    const r = await GeminiService.chat(SELF_CRITIQUE_PROMPT, draft, {
      temperature: 0.8, maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `self_critique_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens });
    const next = parseRewritten(r.text);
    if (!next || next === draft) break;
    draft = next;
  }

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M2', description: 'Self-critique loop: model critiques its own prior draft and rewrites', run });
```

- [ ] **Step 3: Register, TS check, run T1, commit**

```bash
# add `import './M2_self_critique';` to methods/index.ts
cd backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M2 --text T1 --copyscape true --out ../bench-results/M2.json
cd /Users/caonguyenvan/project/dothesis-M2
git add backend/src/services/humanizer/methods bench-results/M2.json
git commit -m "feat(humanizer): M2 self-critique loop + round-1 T1 result"
git push -u origin experiment/humanizer-M2-self-critique
```

---

### Task 12: Implement M3 — Adversarial Paraphrase (LLM-proxy guided)

**Worktree:** `experiment/humanizer-M3-adversarial-paraphrase`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M3 -b experiment/humanizer-M3-adversarial-paraphrase feat/humanizer-v8-bakeoff
cd ../dothesis-M3
```

- [ ] **Step 2: Write `methods/M3_adversarial_paraphrase.ts`**

```ts
// backend/src/services/humanizer/methods/M3_adversarial_paraphrase.ts

// M3: Adversarial Paraphrase. Loop: proxy scores draft → if score >= threshold,
// GPT paraphrases AGGRESSIVELY with the proxy's flagged_phrases as targets.
// Each iteration is told its previous proxy score so it knows whether progress
// was made. Inspired by NeurIPS 2025 Adversarial Paraphrasing (arxiv 2506.07001),
// but with an LLM proxy in place of the real detector — Copyscape never runs
// inside this pipeline.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 4;
const PROXY_TARGET = 30;

const ADVERSARIAL_PROMPT = `You are an aggressive paraphraser. The user supplies:
- TEXT: the current draft
- PROXY_SCORE: a 0-100 estimate of how AI-generated it sounds (higher = worse)
- FLAGGED: phrases that triggered the proxy

Rewrite the TEXT to drive the score down. Prioritize:
1. LEXICAL DIVERSITY — replace generic words with unexpected but apt synonyms
2. CLAUSE REORDERING — change subject-verb-object patterns; lead with subordinate clauses sometimes
3. BURSTINESS — alternate short punchy sentences with long winding ones
4. Fix every FLAGGED phrase

Preserve meaning. Output strict JSON: { "rewrittenText": "<paraphrased text>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial Gemini draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  let lastScore = 100;
  for (let i = 0; i < MAX_LOOPS; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `proxy_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < PROXY_TARGET) break;
    if (proxy.score >= lastScore && i > 0) break; // stop if no progress
    lastScore = proxy.score;

    const userMsg = `TEXT:\n${draft}\n\nPROXY_SCORE: ${proxy.score}\n\nFLAGGED:\n${JSON.stringify(proxy.flagged)}`;
    const para = await OpenAIService.chat(ADVERSARIAL_PROMPT, userMsg, {
      maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `paraphrase_${i+1}`, model: 'gpt-5.5', inputTokens: para.usage.inputTokens, outputTokens: para.usage.outputTokens });
    const next = parseRewritten(para.text);
    if (!next) break;
    draft = next;
  }

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M3', description: 'Adversarial paraphrase guided by LLM AI-likelihood proxy', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append after the `M0` import:

```ts
import './M3_adversarial_paraphrase';
```

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M3/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M3 --text T1 --copyscape true --out ../bench-results/M3.json
cd /Users/caonguyenvan/project/dothesis-M3
git add backend/src/services/humanizer/methods bench-results/M3.json
git commit -m "feat(humanizer): M3 adversarial paraphrase + round-1 T1 result"
git push -u origin experiment/humanizer-M3-adversarial-paraphrase
```

---

### Task 13: Implement M4 — Burstiness Forcer

**Worktree:** `experiment/humanizer-M4-burstiness-forcer`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M4 -b experiment/humanizer-M4-burstiness-forcer feat/humanizer-v8-bakeoff
cd ../dothesis-M4
```

- [ ] **Step 2: Write `methods/M4_burstiness_forcer.ts`**

```ts
// backend/src/services/humanizer/methods/M4_burstiness_forcer.ts

// M4: Burstiness Forcer. Hits the burstiness signal directly with a deterministic
// transform between LLM passes. After Gemini rewrite, measure σ; if σ < 7 (AI
// range), apply burstify(); repeat up to 3 times until σ ≥ 8. Then a light
// Gemini polish (low temp, instructed to PRESERVE burstiness, fix only grammar).

import { GeminiService } from '../../ai/gemini.service';
import { burstify } from '../burstify/burstify';
import { sentenceLengthSigma } from '../stylometric/scorer';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const TARGET_SIGMA = 8;
const MAX_BURSTIFY_TRIES = 3;

const PRESERVING_POLISH_PROMPT = `Polish the user's text for grammar and clarity ONLY. Critical constraints:
- Do NOT make sentence lengths uniform. Keep short sentences short and long sentences long.
- Do NOT remove em dashes, semicolons, or fragmented sentences — they are intentional.
- Fix only obvious grammar errors and awkward word choice.
Output strict JSON: { "rewrittenText": "<polished>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Stage 1: Gemini rewrite
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  // Burstify loop (deterministic, no LLM cost)
  for (let i = 0; i < MAX_BURSTIFY_TRIES; i++) {
    const sigma = sentenceLengthSigma(draft);
    if (sigma >= TARGET_SIGMA) break;
    draft = burstify(draft, { seed: 1 + i });
  }

  // Stage 2: Preserving polish
  const polish = await GeminiService.chat(PRESERVING_POLISH_PROMPT, draft, {
    temperature: 0.3, maxTokens: 4096, jsonMode: true,
  });
  draft = parseRewritten(polish.text) || draft;
  tokens.push({ step: 'gemini_polish', model: 'gemini-3-flash-preview', inputTokens: polish.usage.inputTokens, outputTokens: polish.usage.outputTokens });

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M4', description: 'Burstiness forcer: deterministic σ-widening between LLM passes', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append `import './M4_burstiness_forcer';` after the M0 import.

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M4/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M4 --text T1 --copyscape true --out ../bench-results/M4.json
cd /Users/caonguyenvan/project/dothesis-M4
git add backend/src/services/humanizer/methods bench-results/M4.json
git commit -m "feat(humanizer): M4 burstiness forcer + round-1 T1 result"
git push -u origin experiment/humanizer-M4-burstiness-forcer
```

---

### Task 14: Implement M5 — N-Best Sampling + Stylometric Judge

**Worktree:** `experiment/humanizer-M5-n-best`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M5 -b experiment/humanizer-M5-n-best feat/humanizer-v8-bakeoff
cd ../dothesis-M5
```

- [ ] **Step 2: Write `methods/M5_n_best.ts`**

```ts
// backend/src/services/humanizer/methods/M5_n_best.ts

// M5: N-Best. Generate 5 candidate drafts in parallel with varied configs,
// then pick the lowest-stylometric-score one. The stylometric scorer is
// deterministic and free — Copyscape never runs inside this method.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stylometricScore } from '../stylometric/scorer';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

type Candidate = { text: string; tokens: MethodTokenStep[]; label: string };

async function genGemini(input: string, opts: MethodOptions, temperature: number, label: string): Promise<Candidate> {
  const r = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature, maxTokens: 4096, jsonMode: true,
  });
  return {
    text: parseRewritten(r.text) || input,
    tokens: [{ step: `gemini_${label}`, model: 'gemini-3-flash-preview', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens }],
    label,
  };
}

async function genGptThenGemini(input: string, opts: MethodOptions): Promise<Candidate> {
  const a = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), input, { maxTokens: 4096, jsonMode: true });
  const aText = parseRewritten(a.text) || input;
  const b = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), aText, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  return {
    text: parseRewritten(b.text) || aText,
    tokens: [
      { step: 'gpt_first', model: 'gpt-5.5', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens },
      { step: 'gemini_second', model: 'gemini-3-flash-preview', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens },
    ],
    label: 'gpt_then_gemini',
  };
}

async function genGeminiThenGpt(input: string, opts: MethodOptions): Promise<Candidate> {
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  const aText = parseRewritten(a.text) || input;
  const b = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), aText, { maxTokens: 4096, jsonMode: true });
  return {
    text: parseRewritten(b.text) || aText,
    tokens: [
      { step: 'gemini_first', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens },
      { step: 'gpt_second', model: 'gpt-5.5', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens },
    ],
    label: 'gemini_then_gpt',
  };
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const candidates = await Promise.all([
    genGemini(input, opts, 0.7, 'temp07'),
    genGemini(input, opts, 0.9, 'temp09'),
    genGemini(input, opts, 1.1, 'temp11'),
    genGptThenGemini(input, opts),
    genGeminiThenGpt(input, opts),
  ]);

  // Pick lowest stylometric score (more human-like)
  let best = candidates[0];
  let bestScore = stylometricScore(best.text);
  for (const c of candidates.slice(1)) {
    const s = stylometricScore(c.text);
    if (s < bestScore) { best = c; bestScore = s; }
  }

  // Aggregate tokens from all candidates so cost is reported honestly
  const allTokens = candidates.flatMap(c => c.tokens);

  return { output: best.text, tokenSteps: allTokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M5', description: 'N-best (5 drafts in parallel) ranked by stylometric scorer', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append `import './M5_n_best';` after the M0 import.

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M5/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M5 --text T1 --copyscape true --out ../bench-results/M5.json
cd /Users/caonguyenvan/project/dothesis-M5
git add backend/src/services/humanizer/methods bench-results/M5.json
git commit -m "feat(humanizer): M5 n-best sampling + round-1 T1 result"
git push -u origin experiment/humanizer-M5-n-best
```

---

### Task 15: Implement M6 — Sentence-Surgical Rewrite

**Worktree:** `experiment/humanizer-M6-sentence-surgical`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M6 -b experiment/humanizer-M6-sentence-surgical feat/humanizer-v8-bakeoff
cd ../dothesis-M6
```

- [ ] **Step 2: Write `methods/M6_sentence_surgical.ts`**

```ts
// backend/src/services/humanizer/methods/M6_sentence_surgical.ts

// M6: Sentence-Surgical. Don't rewrite already-human sentences. Get a draft,
// split into sentences, score each via a per-sentence LLM classifier
// (NOT Copyscape), rewrite only the worst 30%, stitch back, light polish.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const PER_SENTENCE_PROMPT = `Score how AI-generated EACH sentence sounds (0-10, higher = more AI).
Input: a JSON array of sentences.
Output: a JSON array of integer scores in the same order. No prose, no explanations.
Example input: ["Hello.", "I utilize quantum entanglement to facilitate workflow."]
Example output: [1, 9]`;

const SURGICAL_REWRITE_PROMPT = `Rewrite the SENTENCE in the context of the surrounding paragraph so it sounds
human. Make it noticeably different in length or rhythm from its neighbors.
Use unexpected word choices. Output strict JSON: { "rewrittenSentence": "<text>" }`;

const POLISH_PROMPT = `The user's text was edited sentence-by-sentence. Some transitions may be rough.
Smooth the transitions ONLY. Do not rewrite content. Do not regularize sentence
length. Output strict JSON: { "rewrittenText": "<smoothed>" }`;

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  const sentences = splitSentences(draft);
  if (sentences.length < 3) return { output: draft, tokenSteps: tokens };

  // Per-sentence scoring (single batched call)
  const scoreCall = await GeminiService.chat(PER_SENTENCE_PROMPT, JSON.stringify(sentences), {
    temperature: 0.1, maxTokens: 1024, jsonMode: true,
  });
  tokens.push({ step: 'sentence_scoring', model: 'gemini-3-flash-preview', inputTokens: scoreCall.usage.inputTokens, outputTokens: scoreCall.usage.outputTokens });
  const scores: number[] = parseScores(scoreCall.text, sentences.length);

  // Pick worst 30% (at least 1, at most 5)
  const n = Math.max(1, Math.min(5, Math.ceil(sentences.length * 0.3)));
  const worstIdx = scores
    .map((s, i) => ({ s, i }))
    .sort((a, b) => b.s - a.s)
    .slice(0, n)
    .map(x => x.i);

  // Rewrite each worst sentence in parallel with surrounding context
  const rewrites = await Promise.all(worstIdx.map(async (idx) => {
    const ctx = sentences.slice(Math.max(0, idx - 1), idx + 2).join(' ');
    const userMsg = `PARAGRAPH_CONTEXT: ${ctx}\n\nSENTENCE: ${sentences[idx]}`;
    const r = await OpenAIService.chat(SURGICAL_REWRITE_PROMPT, userMsg, { maxTokens: 256, jsonMode: true });
    tokens.push({ step: `surgical_${idx}`, model: 'gpt-5.5', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens });
    const stripped = r.text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
    try {
      const parsed = JSON.parse(stripped);
      return { idx, replacement: typeof parsed.rewrittenSentence === 'string' ? parsed.rewrittenSentence : sentences[idx] };
    } catch { return { idx, replacement: sentences[idx] }; }
  }));

  for (const { idx, replacement } of rewrites) sentences[idx] = replacement;
  draft = sentences.join(' ');

  // Light polish for transitions
  const polish = await GeminiService.chat(POLISH_PROMPT, draft, { temperature: 0.3, maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(polish.text) || draft;
  tokens.push({ step: 'transition_polish', model: 'gemini-3-flash-preview', inputTokens: polish.usage.inputTokens, outputTokens: polish.usage.outputTokens });

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

function parseScores(raw: string, expectedLen: number): number[] {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const arr = JSON.parse(stripped);
    if (Array.isArray(arr) && arr.length === expectedLen) return arr.map(x => Number(x) || 0);
  } catch {}
  return new Array(expectedLen).fill(5);
}

registerMethod({ id: 'M6', description: 'Sentence-surgical: per-sentence scoring + targeted rewrites of worst 30%', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append `import './M6_sentence_surgical';` after the M0 import.

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M6/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M6 --text T1 --copyscape true --out ../bench-results/M6.json
cd /Users/caonguyenvan/project/dothesis-M6
git add backend/src/services/humanizer/methods bench-results/M6.json
git commit -m "feat(humanizer): M6 sentence-surgical + round-1 T1 result"
git push -u origin experiment/humanizer-M6-sentence-surgical
```

---

### Task 16: Implement M7 — Voice-Anchoring (Few-Shot Human Style)

**Worktree:** `experiment/humanizer-M7-voice-anchoring`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M7 -b experiment/humanizer-M7-voice-anchoring feat/humanizer-v8-bakeoff
cd ../dothesis-M7
```

- [ ] **Step 2: Write `methods/M7_voice_anchoring.ts`**

```ts
// backend/src/services/humanizer/methods/M7_voice_anchoring.ts

// M7: Voice-Anchoring. Inject 3 paragraphs of confirmed human academic prose as
// few-shot examples; instruct the rewriter to mimic cadence, word choice, and
// punctuation rhythm. Try both anchor sets per call and pick the lower
// stylometric-score output.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stylometricScore } from '../stylometric/scorer';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');
const FORMAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim();
const CASUAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim();

const TEMPLATE = (anchor: string) => `Below are 3 paragraphs written by a human academic. Study their cadence,
sentence-length variance, word choice, and punctuation rhythm. DO NOT copy
phrases — only mimic the style. Then rewrite the user's text in that voice.

EXAMPLES (human prose):
${anchor}

Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const POLISH_TEMPLATE = (anchor: string) => `Polish the user's text to match the voice of these human-written examples.
Fix grammar; preserve sentence-length variance.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<polished>" }`;

async function genWithAnchor(input: string, anchor: string): Promise<{ text: string; tokens: MethodTokenStep[] }> {
  const tokens: MethodTokenStep[] = [];
  const a = await GeminiService.chat(TEMPLATE(anchor), input, { temperature: 0.95, maxTokens: 4096, jsonMode: true });
  tokens.push({ step: 'gemini_anchored_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  let draft = parseRewritten(a.text) || input;
  const b = await OpenAIService.chat(POLISH_TEMPLATE(anchor), draft, { maxTokens: 4096, jsonMode: true });
  tokens.push({ step: 'gpt_anchored_polish', model: 'gpt-5.5', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens });
  draft = parseRewritten(b.text) || draft;
  return { text: draft, tokens };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const [formal, casual] = await Promise.all([genWithAnchor(input, FORMAL), genWithAnchor(input, CASUAL)]);
  const fScore = stylometricScore(formal.text);
  const cScore = stylometricScore(casual.text);
  const winner = fScore <= cScore ? formal : casual;
  return { output: winner.text, tokenSteps: [...formal.tokens, ...casual.tokens] };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

registerMethod({ id: 'M7', description: 'Voice-anchoring: few-shot human prose, formal vs casual, picks lower stylometric', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append `import './M7_voice_anchoring';` after the M0 import.

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M7/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M7 --text T1 --copyscape true --out ../bench-results/M7.json
cd /Users/caonguyenvan/project/dothesis-M7
git add backend/src/services/humanizer/methods bench-results/M7.json
git commit -m "feat(humanizer): M7 voice-anchoring + round-1 T1 result"
git push -u origin experiment/humanizer-M7-voice-anchoring
```

---

### Task 17: Implement M8 — Combo (M1 + M2 + M4)

**Worktree:** `experiment/humanizer-M8-combo`

- [ ] **Step 1: Create worktree**

```bash
cd /Users/caonguyenvan/project/dothesis
git worktree add ../dothesis-M8 -b experiment/humanizer-M8-combo feat/humanizer-v8-bakeoff
cd ../dothesis-M8
```

- [ ] **Step 2: Write `methods/M8_combo.ts`**

```ts
// backend/src/services/humanizer/methods/M8_combo.ts

// M8: Combo. Stacks the three Copyscape-free phases:
//   1. Initial Gemini rewrite + burstify (M4 phase)
//   2. Diagnostic-critic targeted rewrite loop (M1 phase, 2 iterations max)
//   3. Self-critique pass (M2 phase, 1 iteration)
//   4. Final GPT polish
//
// Empirical question: do these stack additively, or do later passes undo
// earlier gains? The bake-off will tell us.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { burstify } from '../burstify/burstify';
import { sentenceLengthSigma } from '../stylometric/scorer';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const TARGETED_PROMPT = `Rewrite ONLY the flagged sentences in FULL_TEXT, addressing each stated reason.
Output strict JSON: { "rewrittenText": "<full text with flagged sentences replaced>" }`;

const SELF_CRITIQUE_PROMPT = `Rewrite the passage. First, silently identify 3 sentences that still sound AI.
Then rewrite the whole passage fixing them. Output strict JSON: { "rewrittenText": "<revised>" }`;

const FINAL_POLISH = `Polish for grammar only. PRESERVE sentence-length variance, em dashes,
fragmented sentences, and unusual word choices. Output strict JSON: { "rewrittenText": "<polished>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Phase A — initial rewrite + burstify
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  if (sentenceLengthSigma(draft) < 8) draft = burstify(draft, { seed: 1 });

  // Phase B — diagnostic-critic targeted rewrites (max 2 iterations)
  for (let i = 0; i < 2; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `critic_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < 30 || proxy.flagged.length === 0) break;
    const userMsg = `FULL_TEXT:\n${draft}\n\nFLAGGED:\n${JSON.stringify(proxy.flagged)}`;
    const fix = await GeminiService.chat(TARGETED_PROMPT, userMsg, { temperature: 0.7, maxTokens: 4096, jsonMode: true });
    tokens.push({ step: `targeted_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: fix.usage.inputTokens, outputTokens: fix.usage.outputTokens });
    draft = parseRewritten(fix.text) || draft;
  }

  // Phase C — single self-critique pass
  const sc = await GeminiService.chat(SELF_CRITIQUE_PROMPT, draft, { temperature: 0.8, maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(sc.text) || draft;
  tokens.push({ step: 'self_critique', model: 'gemini-3-flash-preview', inputTokens: sc.usage.inputTokens, outputTokens: sc.usage.outputTokens });

  // Phase D — final GPT polish
  const p = await OpenAIService.chat(FINAL_POLISH, draft, { maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(p.text) || draft;
  tokens.push({ step: 'gpt_polish', model: 'gpt-5.5', inputTokens: p.usage.inputTokens, outputTokens: p.usage.outputTokens });

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

registerMethod({ id: 'M8', description: 'Combo: rewrite + burstify + critic loop + self-critique + polish', run });
```

- [ ] **Step 3: Register in `methods/index.ts`** — append `import './M8_combo';` after the M0 import.

- [ ] **Step 4: TS check, run T1 with Copyscape, commit, push**

```bash
cd /Users/caonguyenvan/project/dothesis-M8/backend
npx tsc --noEmit
npx ts-node scripts/bench/humanizer-bench.ts --method M8 --text T1 --copyscape true --out ../bench-results/M8.json
cd /Users/caonguyenvan/project/dothesis-M8
git add backend/src/services/humanizer/methods bench-results/M8.json
git commit -m "feat(humanizer): M8 combo + round-1 T1 result"
git push -u origin experiment/humanizer-M8-combo
```

---

## Phase C — Bake-off

### Task 18: Round 1 — aggregate T1 results, identify survivors

**Files:**
- Create: `bench-results/round1-summary.md`

- [ ] **Step 1: Pull all 8 method branches' bench-results into one place**

From the main checkout (`/Users/caonguyenvan/project/dothesis`), fetch each method branch's `bench-results/MX.json` into the local `bench-results/`:

```bash
cd /Users/caonguyenvan/project/dothesis
for m in M1 M2 M3 M4 M5 M6 M7 M8; do
  git fetch origin experiment/humanizer-${m}-*
  git show origin/experiment/humanizer-${m}-*:bench-results/${m}.json > bench-results/${m}.json
done
```

(If branch names don't match the glob exactly, list them with `git branch -r | grep experiment/humanizer-`.)

- [ ] **Step 2: Build round-1 summary**

Write `bench-results/round1-summary.md` with this template, filling in numbers from each `MX.json`:

```markdown
# Round 1 Summary (T1 only)

| Method | scoreIn | scoreOut | drop | tokensIn | tokensOut | duration_ms | survives? |
|--------|---------|----------|------|----------|-----------|-------------|-----------|
| M0 (baseline) | ... | ... | ... | ... | ... | ... | — |
| M1 | ... | ... | ... | ... | ... | ... | yes/no |
| ...

Survivors: methods where scoreOut ≤ 80 AND drop ≥ 30. Drop rule: if no method
survives, lower the bar to top-3 by scoreOut (the deliverable becomes "least
bad").
```

- [ ] **Step 3: Commit**

```bash
git add bench-results/
git commit -m "bench(humanizer): round-1 T1 results across all 8 methods"
```

---

### Task 19: Round 2 — survivors run T2–T5

- [ ] **Step 1: For each survivor branch, run remaining texts**

For each surviving method MX, in its worktree:

```bash
cd /Users/caonguyenvan/project/dothesis-MX/backend
for t in T2 T3 T4 T5; do
  npx ts-node scripts/bench/humanizer-bench.ts --method MX --text $t --copyscape true --out ../bench-results/MX.json
done
git add bench-results/MX.json
git commit -m "bench(humanizer): MX round-2 (T2-T5) results"
git push
```

(This step can be dispatched in parallel via `dispatching-parallel-agents` — one agent per surviving worktree.)

- [ ] **Step 2: Pull all updated `MX.json` files into main checkout**

Same fetch loop as Task 18 step 1.

- [ ] **Step 3: Compute aggregates**

For each method, compute mean / median / max scoreOut across T1-T5. Append to `bench-results/round2-summary.md`:

```markdown
# Round 2 Summary

| Method | mean scoreOut | median | max | mean tokens | mean duration_ms |
|--------|---------------|--------|-----|-------------|-------------------|
| M0     | ... | ... | ... | ... | ... |
| ...    | ... | ... | ... | ... | ... |
```

- [ ] **Step 4: Identify top 2 finalists** (lowest mean scoreOut). Commit summary.

```bash
git add bench-results/round2-summary.md
git commit -m "bench(humanizer): round-2 aggregate across survivors"
```

---

### Task 20: Round 3 — top 2 × 3 reps on T2–T5

- [ ] **Step 1: For each finalist, re-run T2–T5 three more times**

In each finalist's worktree, run T2-T5 three additional times. Each run adds new records to the `MX.json` (the harness appends).

```bash
cd /Users/caonguyenvan/project/dothesis-FINALIST/backend
for rep in 1 2 3; do
  for t in T2 T3 T4 T5; do
    npx ts-node scripts/bench/humanizer-bench.ts --method MX --text $t --copyscape true --out ../bench-results/MX.json
  done
done
git add bench-results/MX.json
git commit -m "bench(humanizer): MX round-3 tiebreak runs"
git push
```

- [ ] **Step 2: Compute per-(method, text) means and overall winner**

In `bench-results/comparison.md`:

```markdown
# Final Comparison

For each finalist, mean scoreOut across {T2, T3, T4, T5} × 4 runs (1 from round 2 + 3 from round 3).

| Method | mean | std dev | mean tokens | mean duration_ms | per-request cost |
|--------|------|---------|-------------|-------------------|-------------------|
| ...    | ...  | ...     | ...         | ...               | ...               |

Per-request cost: estimate using current Gemini + OpenAI pricing, output token-only
weighting at $X/$Y per 1K. Compare against Copyscape per-call price ($Z).

WINNER: <MX> — lowest mean scoreOut at acceptable cost.
```

- [ ] **Step 3: Commit comparison**

```bash
git add bench-results/comparison.md
git commit -m "bench(humanizer): final comparison + winner selection"
```

---

### Task 21: Merge winner to feat branch as v8

- [ ] **Step 1: Merge winner branch into `feat/humanize-crossmodel-perturbation`**

```bash
cd /Users/caonguyenvan/project/dothesis
git checkout feat/humanize-crossmodel-perturbation
git merge experiment/humanizer-MX-<winner-name>
```
Resolve conflicts if any (likely only in `methods/index.ts` if other methods landed).

- [ ] **Step 2: Update `humanizer.service.ts` to call the winner method directly**

Replace the body of `humanizePipeline` to call `getMethod('MX').run(...)` and adapt the return shape to the existing `PipelineResult`. Keep `aiScoreIn` / `aiScoreOut` calls (those are user-facing).

```ts
// In humanizer.service.ts, replace the implementation of humanizePipeline:
import { getMethod } from './methods';

static async humanizePipeline(text: string, tone: string, strength: number, lengthMode: string, onStage?: (stage: string, data: any) => void): Promise<PipelineResult> {
  const aiScoreIn = await this.checkAiScore(text);
  onStage?.('ai_score_in', { score: aiScoreIn });

  const method = getMethod('MX'); // <-- replace MX with winner id
  const result = await method.run(text, { tone, strength, lengthMode });

  const aiScoreOut = await this.checkAiScore(result.output);
  onStage?.('score', { score: aiScoreOut });

  const totalInputTokens = result.tokenSteps.reduce((s, x) => s + x.inputTokens, 0);
  const totalOutputTokens = result.tokenSteps.reduce((s, x) => s + x.outputTokens, 0);

  return {
    rewrittenText: result.output,
    changes: [],
    aiScoreIn,
    aiScoreOut,
    tokenUsage: {
      steps: result.tokenSteps.map(s => ({ step: s.step as any, model: s.model, iteration: 1, inputTokens: s.inputTokens, outputTokens: s.outputTokens })),
      totalInputTokens, totalOutputTokens,
    },
    iterations: 1,
  };
}
```

Also update the file's leading comment block from `Decision (v7)` to `Decision (v8)` with a short note about the bake-off and which method won.

- [ ] **Step 3: TS check + smoke**

```bash
cd backend
npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/humanizer/humanizer.service.ts
git commit -m "feat(humanizer): v8 — winner method MX from bake-off"
```

---

### Task 22: End-to-end smoke test on the original 101-word text

- [ ] **Step 1: Boot dev backend**

```bash
cd /Users/caonguyenvan/project/dothesis
./dev.sh
```
(Run in background or separate terminal.)

- [ ] **Step 2: POST the 101-word text from the user's frustration log to the humanizer endpoint**

Use curl or the frontend `/humanizer` page. Confirm:
- `aiScoreIn` ≈ 99 (matches user's prior run)
- `aiScoreOut` < 50 (acceptance criterion)
- response returns within ~30s

If acceptance fails, document it in `bench-results/comparison.md`'s WINNER section as "did not meet acceptance bar — recommended next steps: [Round 4: prompt iteration on winner / explore method M0 + winner combo / etc.]" and stop. The negative result is the deliverable.

- [ ] **Step 3: Tear down worktrees if winner is selected and merged**

```bash
cd /Users/caonguyenvan/project/dothesis
for d in dothesis-M1 dothesis-M2 dothesis-M3 dothesis-M4 dothesis-M5 dothesis-M6 dothesis-M7 dothesis-M8; do
  git worktree remove --force ../$d 2>/dev/null || true
done
git worktree prune
```

- [ ] **Step 4: Final commit if any cleanup**

```bash
git status
# if anything touched: commit as cleanup(humanizer): tear down bake-off worktrees
```
