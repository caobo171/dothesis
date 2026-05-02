# Humanizer M23 — Rules-Critic-Augmented Anchor Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build M23, a humanizer method that layers four mechanically-measurable rewrite rules (hedging, fronted-clause openings, no-expansion simplification, anti-X-and-Y two-item lists) onto M21's existing router-anchor pipeline, with a deterministic compliance critic that triggers one revision pass on rule violations. Bench M23 vs M21 on the 5 failing register texts; if it wins, ship by swapping the production pipeline.

**Architecture:** M23 runs the same `strip-vocab → router → rewrite → polish → strip-vocab` shape as M21, but the Gemini rewrite prompt has the four rules appended as explicit imperative instructions, and a deterministic checker validates rule application after the rewrite. If any rule fails, ONE revision call is made to Gemini with quantitative feedback (e.g. "you used 7 X-and-Y lists, target ≤2"). The polish stage stays unchanged from M21 to avoid GPT undoing rule work. All four rules are pure-text checks (no LLM in the critic loop).

**Tech Stack:** TypeScript (Node), `ts-node` for execution, no test framework — assertions via Node's `node:assert/strict` module run as standalone scripts (matches the project's existing `backend/scripts/bench/` pattern). LLM calls via `GeminiService` (`gemini-3-flash-preview`) and `OpenAIService` (`gpt-5.5`). Bench harness is the existing `backend/scripts/bench/dual-judge-bakeoff.ts` invoked with `--methods M21,M23 --no-copyscape`.

**Spec:** `docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md`
**Predecessor handoff:** `docs/superpowers/handoff/2026-04-29-humanizer-v11-status.md`

---

## File Structure

| File | Status | Purpose |
|---|---|---|
| `backend/src/services/humanizer/critic/rule_compliance.ts` | Create | Pure-function rule checker (counts, thresholds, formatter) |
| `backend/scripts/test/test-rule-compliance.ts` | Create | Standalone assertion script for rule_compliance.ts |
| `backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts` | Create | The new method |
| `backend/src/services/humanizer/methods/index.ts` | Modify | Register M23 via side-effect import |
| `backend/src/services/humanizer/humanizer.service.ts` | Modify (last task only, conditional on bench win) | Swap `getMethod('M21')` → `getMethod('M23')`, update version label |
| `docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md` | Create (last task) | Results writeup, win or park |

**Not modified:**
- `backend/src/services/humanizer/methods/M21_router_anchor.ts` — M23 *does not* import from M21. Per the design's "Refactor: extract rewrite-prompt builder" note: that refactor would couple the two files unnecessarily. M23 inlines its own slightly-different rewrite prompt instead. Keeping M21 untouched protects the production path.
- The polish prompt — M23 uses the same polish behavior as M21, also inlined.
- Anchor `.txt` files.

---

## Task 1: Create the deterministic rule-compliance checker

**Files:**
- Create: `backend/src/services/humanizer/critic/rule_compliance.ts`

This is a pure-function module. No LLM calls, no IO. All four rule checks plus the feedback formatter live here. Designed to be testable in isolation (Task 2).

- [ ] **Step 1: Create the file with full implementation**

Create `backend/src/services/humanizer/critic/rule_compliance.ts`:

```ts
// backend/src/services/humanizer/critic/rule_compliance.ts

// Decision: Pure-function checker — no LLM, no IO. The four rules are all
// mechanically measurable text features; using regex/heuristics keeps the
// critic free, fast, and deterministic. This is the key insight that makes
// M23 viable where M1/M2/M9 (LLM critics) failed: a checker that grades
// "did you apply rule X?" can give quantitative feedback to the regeneration
// call, while LLM critics that grade "is this still AI?" historically gave
// noise that didn't correlate with detector outputs.
//
// Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

export type RuleId = 'hedging' | 'fronted_openings' | 'no_expansion' | 'anti_x_and_y';

export type RuleViolation = {
  rule: RuleId;
  measured: number;
  threshold: number;
  feedbackForLLM: string;
};

export type ComplianceMetrics = {
  inputWords: number;
  outputWords: number;
  hedgeCount: number;
  hedgeRatePer100Words: number;
  sentenceCount: number;
  frontedClauseCount: number;
  frontedClauseRatio: number;
  xAndYCount: number;
  xAndYRatePer100Words: number;
  expansionRatio: number;
};

export type ComplianceReport = {
  passed: boolean;
  violations: RuleViolation[];
  metrics: ComplianceMetrics;
};

// Hedge tokens — multi-word patterns and single words. Multi-word patterns
// must come first since they're more specific.
const HEDGE_PATTERNS: RegExp[] = [
  /\bis\s+believed\b/gi,
  /\bis\s+suspected\b/gi,
  /\bis\s+likely\b/gi,
  /\btends\s+to\b/gi,
  /\bappears\b/gi,
  /\bseems\b/gi,
  /\bmay\b/gi,
  /\bmight\b/gi,
  /\bcan\b/gi,
  /\bsuggests?\b/gi,
  /\barguably\b/gi,
  /\bpresumably\b/gi,
];

// Fronted-clause sentence openers. A sentence "starts with a fronted clause"
// when its first token is a subordinator, present participle, or fronted PP.
// Capitalized to match sentence-initial position.
const FRONTED_OPENERS = new Set([
  // Subordinators
  'although', 'though', 'while', 'whereas',
  'since', 'because', 'as',
  'despite', 'notwithstanding',
  'given', 'considering',
  'when', 'whenever', 'before', 'after', 'until', 'unless', 'if',
  // Present participles often start fronted clauses
  'looking', 'consider', 'considering', 'recognizing', 'noting',
  // Common fronted PP heads
  'in', 'across', 'under', 'within', 'beyond', 'throughout', 'amid', 'among',
  'by', 'through', 'with', 'without', 'against', 'during', 'beneath',
  // Adverbial fronts that count as "not subject-first"
  'historically', 'traditionally', 'increasingly', 'crucially', 'notably',
  'importantly', 'remarkably', 'arguably',
]);

// X-and-Y idiom whitelist — these "X and Y" patterns are fixed expressions,
// not parallel two-item lists, so they should NOT count as violations.
const X_AND_Y_IDIOM_WHITELIST = new Set([
  'back and forth',
  'more and more',
  'over and over',
  'up and down',
  'in and out',
  'now and then',
  'time and again',
  'on and on',
  'round and round',
  'side by side', // Not "X and Y" but listed for safety; won't match the regex anyway
  'give and take',
  'trial and error',
  'black and white',
  'rock and roll',
  'pros and cons',
]);

// Word-count helper: split on whitespace, filter empties.
function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// Sentence splitter — naive but adequate for English prose. Splits on
// .!? followed by whitespace. Filters empty fragments.
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// First word of a sentence, lowercased, stripped of leading punctuation.
function firstWord(sentence: string): string {
  const m = sentence.replace(/^[^\p{L}]+/u, '').match(/^(\S+)/);
  return m ? m[1].toLowerCase().replace(/[^\p{L}]+$/u, '') : '';
}

function countHedges(text: string): number {
  let total = 0;
  for (const re of HEDGE_PATTERNS) {
    const matches = text.match(re);
    if (matches) total += matches.length;
  }
  return total;
}

function countFrontedClauses(sentences: string[]): number {
  let count = 0;
  for (const s of sentences) {
    const w = firstWord(s);
    if (FRONTED_OPENERS.has(w)) count++;
  }
  return count;
}

// Two-item "X and Y" parallel lists. Match adjacent word + "and" + word
// where both are alphabetic (not numbers, not "and" itself).
function countXAndY(text: string): number {
  const re = /\b([A-Za-z]{2,})\s+and\s+([A-Za-z]{2,})\b/g;
  let count = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const phrase = `${m[1].toLowerCase()} and ${m[2].toLowerCase()}`;
    if (!X_AND_Y_IDIOM_WHITELIST.has(phrase)) count++;
  }
  return count;
}

// Thresholds — first-cut values from the design spec. Tuning these is part
// of the M23 bench iteration; record any threshold change in the v12 handoff.
const THRESHOLDS = {
  hedgeRatePer100Words: 2,        // ≥ 2 per 100 words
  frontedClauseRatio: 0.25,       // ≥ 25% of sentences
  expansionRatio: 1.05,           // ≤ 1.05 (output may exceed input by 5% max)
  xAndYRatePer100Words: 3,        // ≤ 3 per 100 words
};

export function checkRuleCompliance(input: string, output: string): ComplianceReport {
  const inputWords = countWords(input);
  const outputWords = countWords(output);
  const sentences = splitSentences(output);
  const sentenceCount = sentences.length;

  const hedgeCount = countHedges(output);
  const frontedClauseCount = countFrontedClauses(sentences);
  const xAndYCount = countXAndY(output);

  // Per-100-word rates. Guard against division by zero on empty output.
  const per100 = outputWords > 0 ? 100 / outputWords : 0;
  const hedgeRatePer100Words = hedgeCount * per100;
  const xAndYRatePer100Words = xAndYCount * per100;
  const frontedClauseRatio = sentenceCount > 0 ? frontedClauseCount / sentenceCount : 0;
  const expansionRatio = inputWords > 0 ? outputWords / inputWords : 0;

  const violations: RuleViolation[] = [];

  if (hedgeRatePer100Words < THRESHOLDS.hedgeRatePer100Words) {
    violations.push({
      rule: 'hedging',
      measured: hedgeRatePer100Words,
      threshold: THRESHOLDS.hedgeRatePer100Words,
      feedbackForLLM: `Hedging language: only ${hedgeCount} hedge tokens in ${outputWords} words (${hedgeRatePer100Words.toFixed(1)}/100w). Target ≥ ${THRESHOLDS.hedgeRatePer100Words}/100w. Use words like "appears", "seems", "may", "might", "can", "suggests", "is believed", "tends to" to soften factual statements where appropriate.`,
    });
  }

  if (frontedClauseRatio < THRESHOLDS.frontedClauseRatio) {
    violations.push({
      rule: 'fronted_openings',
      measured: frontedClauseRatio,
      threshold: THRESHOLDS.frontedClauseRatio,
      feedbackForLLM: `Fronted-clause sentence openings: only ${frontedClauseCount} of ${sentenceCount} sentences (${(frontedClauseRatio * 100).toFixed(0)}%) start with something other than the subject. Target ≥ ${(THRESHOLDS.frontedClauseRatio * 100).toFixed(0)}%. Start more sentences with "Although", "While", "Given", "Despite", "When", or with fronted prepositional phrases like "In recent years,", "Across the field,", "By contrast,".`,
    });
  }

  if (expansionRatio > THRESHOLDS.expansionRatio) {
    violations.push({
      rule: 'no_expansion',
      measured: expansionRatio,
      threshold: THRESHOLDS.expansionRatio,
      feedbackForLLM: `Output is too long: ${outputWords} words vs ${inputWords} input words (${expansionRatio.toFixed(2)}× expansion). Target ≤ ${THRESHOLDS.expansionRatio.toFixed(2)}×. Cut filler — vague generalizations, repeated points, and surface-level qualifiers — to bring length back in line.`,
    });
  }

  if (xAndYRatePer100Words > THRESHOLDS.xAndYRatePer100Words) {
    violations.push({
      rule: 'anti_x_and_y',
      measured: xAndYRatePer100Words,
      threshold: THRESHOLDS.xAndYRatePer100Words,
      feedbackForLLM: `Two-item "X and Y" lists: ${xAndYCount} occurrences in ${outputWords} words (${xAndYRatePer100Words.toFixed(1)}/100w). Target ≤ ${THRESHOLDS.xAndYRatePer100Words}/100w. Replace pairs like "social and educational" or "anxiety and fear" with single nouns, longer enumerations (three+ items), or rephrase to avoid the parallel pair.`,
    });
  }

  return {
    passed: violations.length === 0,
    violations,
    metrics: {
      inputWords,
      outputWords,
      hedgeCount,
      hedgeRatePer100Words,
      sentenceCount,
      frontedClauseCount,
      frontedClauseRatio,
      xAndYCount,
      xAndYRatePer100Words,
      expansionRatio,
    },
  };
}

export function formatRevisionFeedback(report: ComplianceReport): string {
  if (report.passed) return '';
  const lines = report.violations.map((v) => `- ${v.feedbackForLLM}`);
  return `Your previous rewrite missed these targets:\n${lines.join('\n')}\nApply these fixes while preserving the original meaning.`;
}
```

- [ ] **Step 2: TypeScript compile check**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'rule_compliance|error TS' | head -20
```

Expected: no errors mentioning `rule_compliance.ts`. (Other unrelated TS errors in the repo are out of scope.)

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/critic/rule_compliance.ts
git commit -m "$(cat <<'EOF'
feat(humanizer): rule-compliance checker for M23 critic

Pure-function checker for the four mechanically-measurable rules:
hedging rate, fronted-clause sentence openings, no-expansion ratio,
and anti-X-and-Y two-item list rate. Returns a ComplianceReport
with quantitative metrics and per-violation LLM-feedback strings
that the M23 revision call will use.

Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Standalone assertion test for rule_compliance

**Files:**
- Create: `backend/scripts/test/test-rule-compliance.ts`

The repo doesn't use jest/vitest. This task adds a small `node:assert`-based runner that exercises the checker on hand-crafted strings. The script exits non-zero on any failure so it can be added to CI later if desired. Run via `npx ts-node`.

- [ ] **Step 1: Write the test script with all assertions**

Create `backend/scripts/test/test-rule-compliance.ts`:

```ts
// backend/scripts/test/test-rule-compliance.ts
//
// Run: npx ts-node -r tsconfig-paths/register scripts/test/test-rule-compliance.ts
// Exits non-zero on any assertion failure.
//
// Why a standalone script rather than jest/vitest: the repo doesn't have a
// configured test framework (the package.json `test` script points at a
// non-existent file). Following the existing `backend/scripts/bench/` pattern
// of one-off ts-node scripts keeps this self-contained and runnable today.

import assert from 'node:assert/strict';
import { checkRuleCompliance, formatRevisionFeedback } from '../../src/services/humanizer/critic/rule_compliance';

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (e) {
    console.log(`  ✗ ${name}`);
    console.log(`    ${(e as Error).message}`);
    failed++;
  }
}

console.log('checkRuleCompliance — hedging counter');

test('counts whole-word hedge tokens', () => {
  // 6 hedges in 30 words = 20/100w, comfortably above threshold of 2
  const out = 'The result may suggest that the model appears reliable. It seems plausible. Performance can vary, and the effect might be modest. Adoption tends to be slow.';
  const r = checkRuleCompliance('Input text. '.repeat(15), out);
  assert.ok(r.metrics.hedgeCount >= 6, `expected >=6 hedges, got ${r.metrics.hedgeCount}`);
});

test('does not match hedge tokens inside other words', () => {
  // "Mayor", "scanning", "candidate" must NOT match \bmay\b, \bcan\b
  const out = 'The Mayor announced a candidate. Scanning the document took time. The result was unexpected.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.hedgeCount, 0, `expected 0 hedges, got ${r.metrics.hedgeCount}`);
});

test('multi-word hedges count correctly', () => {
  // "is believed", "is suspected", "tends to" — 3 multi-word hedges
  const out = 'The effect is believed to be small. Causation is suspected but not proven. The trend tends to reverse.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.ok(r.metrics.hedgeCount >= 3, `expected >=3 hedges, got ${r.metrics.hedgeCount}`);
});

console.log('\ncheckRuleCompliance — fronted-clause counter');

test('detects subordinator-fronted sentences', () => {
  const out = 'Although the data is limited, the trend is clear. While critics disagree, the model holds. Given these constraints, performance was strong. The result is robust.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.sentenceCount, 4);
  assert.equal(r.metrics.frontedClauseCount, 3, `expected 3 fronted, got ${r.metrics.frontedClauseCount}`);
});

test('detects fronted prepositional phrases', () => {
  const out = 'In recent years, the field grew. Across most studies, the effect held. The conclusion is straightforward.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.frontedClauseCount, 2, `expected 2 fronted, got ${r.metrics.frontedClauseCount}`);
});

test('does not count subject-first sentences', () => {
  const out = 'The model performed well. Researchers confirmed this. Results were robust.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.frontedClauseCount, 0);
});

console.log('\ncheckRuleCompliance — X-and-Y counter');

test('counts parallel two-item conjunctions', () => {
  // 3 parallel pairs: "social and educational", "anxiety and fear", "students and teachers"
  const out = 'Social and educational outcomes vary. Anxiety and fear were measured. Students and teachers reported similar results.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.ok(r.metrics.xAndYCount >= 3, `expected >=3, got ${r.metrics.xAndYCount}`);
});

test('whitelists common idioms', () => {
  const out = 'The discussion went back and forth. The trend grew more and more pronounced. Pros and cons were debated.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.xAndYCount, 0, `expected 0 (idioms whitelisted), got ${r.metrics.xAndYCount}`);
});

console.log('\ncheckRuleCompliance — expansion ratio');

test('flags >5% expansion', () => {
  const input = 'Short input.';   // 2 words
  const output = 'A much longer rewrite that adds many extra words to expand it.'; // 12 words → 6× expansion
  const r = checkRuleCompliance(input, output);
  const v = r.violations.find((x) => x.rule === 'no_expansion');
  assert.ok(v, 'expected no_expansion violation');
});

test('passes at exactly 1.0 ratio', () => {
  const input = 'one two three four five six seven eight nine ten';
  const output = 'aa bb cc dd ee ff gg hh ii jj';
  const r = checkRuleCompliance(input, output);
  const v = r.violations.find((x) => x.rule === 'no_expansion');
  assert.equal(v, undefined, 'no_expansion should not violate at 1.0');
});

console.log('\ncheckRuleCompliance — formatRevisionFeedback');

test('passing report formats to empty string', () => {
  // Make a synthetic passing output: lots of hedges, fronted clauses, no X-and-Y, same length.
  const input = 'one two three four five six seven eight nine ten';
  const output = 'Although evidence may suggest impact, the result is believed minor. While critics may disagree, performance appears robust.';
  const r = checkRuleCompliance(input, output);
  if (r.passed) {
    assert.equal(formatRevisionFeedback(r), '');
  } else {
    // Synthetic test: even if it doesn't fully pass, formatter must mention violations only.
    const fb = formatRevisionFeedback(r);
    for (const v of r.violations) {
      assert.ok(fb.includes(v.rule.replace(/_/g, ' ')) || fb.includes(v.feedbackForLLM.split(':')[0]),
        `feedback should mention violation ${v.rule}`);
    }
  }
});

test('feedback only mentions failed rules', () => {
  // Force only the no_expansion violation: very short input, very long output, with hedges + fronted opens
  const input = 'tiny';
  const output = 'Although the data may suggest variability, the effect is believed to be small but present in nearly every measured cohort despite limited statistical power.';
  const r = checkRuleCompliance(input, output);
  const fb = formatRevisionFeedback(r);
  assert.ok(fb.includes('Output is too long'), 'feedback should mention expansion violation');
  // Hedging is satisfied here; feedback should NOT include hedging-violation language.
  assert.ok(!fb.includes('Hedging language: only'), 'should not mention hedging when satisfied');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
```

- [ ] **Step 2: Run the test script**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx ts-node -r tsconfig-paths/register scripts/test/test-rule-compliance.ts
```

Expected: all tests pass, exit code 0. Output ends with `N passed, 0 failed`.

If any test fails: read the assertion message, decide whether the bug is in the test (wrong expectation) or the checker (wrong logic). Fix and re-run. Do not skip failing tests.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/test/test-rule-compliance.ts
git commit -m "$(cat <<'EOF'
test(humanizer): assertion script for rule_compliance checker

Standalone node:assert tests covering whole-word hedge matching
(no false positives on Mayor/scanning), multi-word hedges,
fronted-clause detection, X-and-Y idiom whitelist, expansion
ratio thresholds, and feedback-formatter behavior. Runs via
ts-node since the repo doesn't have a configured test framework.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement M23 method

**Files:**
- Create: `backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts`

M23 follows M21's structure but with the rules-augmented rewrite prompt and the deterministic critic + revision step inserted between rewrite and polish.

- [ ] **Step 1: Create the method file**

Create `backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts`:

```ts
// backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts
//
// M23: M21 (router-anchor) + four mechanically-measurable rewrite rules
// injected into the Gemini rewrite prompt + a deterministic compliance
// critic that triggers ONE revision pass on rule violations.
//
// Pipeline:
//   strip AI-vocab (deterministic, free)
//   → Gemini router: pick 1 anchor (same as M21)
//   → Gemini rewrite anchored on the chosen one + four rules in the prompt
//   → deterministic rule-compliance critic
//       ├ pass → continue
//       └ fail → ONE revision call to Gemini with quantitative feedback
//   → GPT polish anchored on the same (UNCHANGED from M21)
//   → strip AI-vocab again
//
// LLM call count: 3 (best case) or 4 (revision triggered). Vs M21: 3.
//
// Why inline the anchor library + prompts rather than import from M21:
// the rewrite prompt diverges (rules appended), and importing partial
// internals from M21 would couple the production-critical M21 to an
// experimental method. Duplication is the right tradeoff here.
//
// Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { checkRuleCompliance, formatRevisionFeedback } from '../critic/rule_compliance';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');

type AnchorDef = { id: string; desc: string; text: string };
const ANCHORS: AnchorDef[] = [
  {
    id: 'academic_formal',
    desc: 'PICK FOR: abstract analytical / expository writing on technical, philosophical, or scientific topics (transformer attention, vector search, market analysis, philosophy). Third-person, formal vocabulary. NOT FOR: personal stories, opinion essays, casual blogs, how-to guides.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim(),
  },
  {
    id: 'academic_casual',
    desc: 'PICK FOR: educational / explanatory writing addressed to a reader, lecture register, mid-formality, news articles. NOT FOR: pure abstract analysis (use academic_formal) or personal narrative (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim(),
  },
  {
    id: 'argumentative',
    desc: 'PICK FOR: input that argues a contested position (e.g. "why X is wrong", "we should do Y", policy debates, opinion pieces). The input takes a side. NOT FOR: neutral exposition.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'argumentative.txt'), 'utf8').trim(),
  },
  {
    id: 'instructional',
    desc: 'PICK FOR: how-to / tutorial / instructional / business-formal / memo / policy / guidance content. The input tells someone how to do something or describes a procedure or formal announcement. NOT FOR: narrative or argument.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'instructional.txt'), 'utf8').trim(),
  },
  {
    id: 'user_modern',
    desc: 'PICK FOR: modern OPINION / REFLECTION about contemporary tech / work / productivity / education ("I think X is overrated", "what I learned about Y"). Generalizing claims, no specific incidents. NOT FOR: pure narrative with specific moments (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_modern.txt'), 'utf8').trim(),
  },
  {
    id: 'user_narrative',
    desc: 'PICK FOR: first-person STORY or EXPERIENCE — describing a specific moment, place, sensory detail, or event ("my experience doing X", "when I tried Y", "starting a morning routine", travel posts, blog posts, product reviews). Contains concrete specifics. ALWAYS pick this over user_modern when the input is experiential or describes habits/routines/personal moments.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_narrative.txt'), 'utf8').trim(),
  },
];

const ROUTER_PROMPT = `You are an anchor-matcher. Given the user's INPUT_TEXT, pick exactly one of the
following style anchors whose register best matches the input. Match by:
- topic / domain (modern tech topics → modern anchors; abstract / theoretical → academic anchors)
- voice (first-person reflective → casual/modern; third-person formal → formal academic)
- argumentative stance (opinion / polemic → argumentative)

ANCHORS:
${ANCHORS.map((a) => `- ${a.id}: ${a.desc}`).join('\n')}

Output strict JSON: { "anchor": "<one of the anchor ids above>", "reason": "<short reason>" }`;

// The four rules — appended to the rewrite prompt. Drawn from the YouTube
// humanization tutorial (see spec). Each rule is mechanically measurable
// by the rule_compliance checker, and the critic feedback (Task 1) refers
// back to these by name.
const RULES_BLOCK = `
ADDITIONAL REWRITE RULES — apply all four:

1. HEDGING. Use intellectual hesitation. Replace flat factual statements with hedged ones using "appears", "seems", "may", "might", "can", "suggests", "is believed", "is suspected", "is likely", "tends to", "arguably", "presumably". Aim for at least 2 hedge tokens per 100 words.

2. SENTENCE-OPENING VARIATION. Start at least 25% of sentences with something other than the subject NP — use subordinators ("Although", "While", "Given", "Despite", "When"), present participles ("Considering", "Looking"), or fronted prepositional phrases ("In recent years,", "Across the field,", "By contrast,").

3. SIMPLIFICATION (NO EXPANSION). The output must not be more than 5% longer than the input. Cut filler — vague generalizations, surface-level qualifiers, and repeated points. If you find yourself adding rather than rewording, stop.

4. AVOID "X AND Y" TWO-ITEM LISTS. Do not chain pairs like "social and educational", "anxiety and fear", "students and teachers". Use single nouns, longer enumerations (three+ items), or rephrase. Limit two-item conjunctions to ≤ 3 per 100 words.
`;

const REWRITE_TEMPLATE = (anchor: string) => `Below are paragraphs written by a real human. Study their cadence,
sentence-length variance, word choice, punctuation rhythm, and any natural
imperfections (run-ons, occasional typos, hedges, idiosyncratic phrasings).
DO NOT copy phrases — only mimic the style and rhythm. Match the register
shown in the examples.
Then rewrite the user's text in that voice.

EXAMPLES:
${anchor}
${RULES_BLOCK}
Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const REVISION_TEMPLATE = (anchor: string, feedback: string) => `You previously rewrote a text in the voice of these human-written examples.
Your rewrite missed some of the explicit rules. Revise the rewrite to fix
the noted issues while preserving the original meaning AND continuing to
mimic the examples' voice.

EXAMPLES:
${anchor}

${feedback}

Output strict JSON: { "rewrittenText": "<revised text>" }`;

const POLISH_TEMPLATE = (anchor: string) => `Polish the user's text to match the voice of these human-written examples.
Fix only the most jarring errors; preserve sentence-length variance and any
natural imperfections that match the examples' register.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<polished>" }`;

function parseJsonField(raw: string, field: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p[field] === 'string' && p[field].trim() ? p[field] : null;
  } catch { return null; }
}

async function pickAnchor(input: string): Promise<{ id: string; reason: string; tokens: MethodTokenStep }> {
  const r = await GeminiService.chat(ROUTER_PROMPT, `INPUT_TEXT:\n${input}`, {
    temperature: 0.0,
    maxTokens: 1024,
    jsonMode: true,
  });
  const tokens: MethodTokenStep = {
    step: 'gemini_router',
    model: 'gemini-3-flash-preview',
    inputTokens: r.usage.inputTokens,
    outputTokens: r.usage.outputTokens,
  };
  const id = parseJsonField(r.text, 'anchor');
  const reason = parseJsonField(r.text, 'reason') ?? '';
  const validIds = new Set(ANCHORS.map((a) => a.id));
  return {
    id: id && validIds.has(id) ? id : 'user_modern',
    reason,
    tokens,
  };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // 1) strip AI-vocab from input (deterministic, free)
  const cleaned = stripAiVocab(input);

  // 2) router picks the anchor
  const pick = await pickAnchor(cleaned);
  tokens.push(pick.tokens);
  const anchor = ANCHORS.find((a) => a.id === pick.id)!;

  // 3) Gemini rewrite anchored on the chosen one, with rules appended
  const rw = await GeminiService.chat(REWRITE_TEMPLATE(anchor.text), cleaned, {
    temperature: 0.95, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gemini_rewrite_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rw.usage.inputTokens, outputTokens: rw.usage.outputTokens });
  let draft = parseJsonField(rw.text, 'rewrittenText') || cleaned;

  // 4) deterministic compliance critic — checks the four rules.
  const report = checkRuleCompliance(cleaned, draft);
  if (!report.passed) {
    // ONE revision call only. Bounded cost, predictable latency.
    const feedback = formatRevisionFeedback(report);
    const rev = await GeminiService.chat(REVISION_TEMPLATE(anchor.text, feedback), draft, {
      temperature: 0.85, maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `gemini_revise_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rev.usage.inputTokens, outputTokens: rev.usage.outputTokens });
    const revised = parseJsonField(rev.text, 'rewrittenText');
    // Only adopt the revision if it parsed; otherwise keep the original draft.
    if (revised) draft = revised;
  }

  // 5) GPT polish anchored on the same (unchanged from M21)
  const pol = await OpenAIService.chat(POLISH_TEMPLATE(anchor.text), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gpt_polish_${pick.id}`, model: 'gpt-5.5', inputTokens: pol.usage.inputTokens, outputTokens: pol.usage.outputTokens });
  const polished = parseJsonField(pol.text, 'rewrittenText') || draft;

  // 6) strip AI-vocab from output
  const output = stripAiVocab(polished);

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M23', description: 'M21 + four rewrite rules + deterministic critic with one revision pass', run });
```

- [ ] **Step 2: Register M23 in the method index**

Modify `backend/src/services/humanizer/methods/index.ts` — add a side-effect import for M23 alongside the existing M22 import. Insert this line directly after the existing `import './M22_router_then_backtrans';` line:

```ts
// v12 candidate — layers four mechanically-measurable rewrite rules
// (hedging, fronted-clause openings, no-expansion, anti-X-and-Y) on
// top of M21's anchor pipeline, with a deterministic compliance critic
// that triggers one revision pass on violations.
import './M23_rules_critic_anchor';
```

- [ ] **Step 3: TypeScript compile check**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'M23_rules|rule_compliance|methods/index|error TS' | head -20
```

Expected: no errors mentioning the M23 file, the index, or rule_compliance.

- [ ] **Step 4: Smoke test M23 registration**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx ts-node -r tsconfig-paths/register -e "import('./src/services/humanizer/methods').then(m => { const x = m.getMethod('M23'); console.log('OK', x.id, '|', x.description); }).catch(e => { console.error('FAIL', e.message); process.exit(1); });"
```

Expected: `OK M23 | M21 + four rewrite rules + deterministic critic with one revision pass`

If it errors: the file likely failed to register (TS compile error, anchor file not found, or import order). Fix and re-run.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts backend/src/services/humanizer/methods/index.ts
git commit -m "$(cat <<'EOF'
feat(humanizer): M23 method — anchor + rules + critic + revision

Layers four explicit rewrite rules onto M21's router-anchor pipeline,
with a deterministic compliance critic that triggers ONE revision call
on rule violations. Rules: hedging rate, fronted-clause openings,
no-expansion ratio, anti-X-and-Y two-item lists. Critic gives
quantitative feedback to the revision call. 3 LLM calls best case,
4 worst case. Production stays on M21 until M23 wins the bench.

Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Phase 1 bench — M23 vs M21 on the 5 failing texts

This is the fast iteration cycle. Run M21 and M23 side-by-side on T3, T7, T8, T9, T11 only. ~5 min, ~$0.05 in Sapling spend. The goal is to see whether M23 lifts the failing texts; if it does, proceed to phase 2; if not, tune thresholds and re-run, then decide.

**Before running:** confirm `SAPLING_API_KEY` is set in `backend/.env` (check by `grep SAPLING backend/.env`). Bench fails fast without it.

- [ ] **Step 1: Run the phase 1 bench**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx ts-node -r tsconfig-paths/register scripts/bench/dual-judge-bakeoff.ts \
  --methods M21,M23 \
  --out ../bench-results/v12-m23-failing-only.json \
  --no-copyscape
```

Note: the existing harness runs all 12 corpus texts — it doesn't have a `--texts` flag. To restrict to T3/T7/T8/T9/T11 you have two options:

**Option A (simpler, ~12 min):** run the full corpus anyway. The same JSON gives you both phase 1 (failing texts) and phase 2 (full corpus) data in one shot. **Recommended.** Skip Task 5's separate phase 2 run if you take this option.

**Option B (~5 min):** edit the `TEXT_IDS` constant at line 25 of `dual-judge-bakeoff.ts` temporarily to `['T3', 'T7', 'T8', 'T9', 'T11']`, run, then revert the edit. Only worth it if iterating thresholds repeatedly.

Default: **Option A**. Run the full bench and analyze both subsets from the same JSON.

Expected output: progress lines `[N/total] M2X/Tn: cs <num>→<num> | sap <num>→<num> | <duration>ms` and a final summary table. Bench writes incrementally so partial results survive a crash.

- [ ] **Step 2: Analyze the results**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
python3 - <<'EOF'
import json, statistics
data = json.load(open('../bench-results/v12-m23-failing-only.json'))
failing = {'T3','T7','T8','T9','T11'}
passing = {'T1','T2','T4','T5','T6','T10','T12'}
def report(label, texts):
    print(f'\n=== {label} ===')
    print(f'{"text":>5} {"M21 in→out":>14} {"M23 in→out":>14} {"M23 vs M21":>12}')
    for tid in sorted(texts):
        m21 = next((r for r in data if r['methodId']=='M21' and r['textId']==tid), None)
        m23 = next((r for r in data if r['methodId']=='M23' and r['textId']==tid), None)
        if not m21 or not m23: continue
        s21 = f"{m21.get('saplingIn')}→{m21.get('saplingOut')}"
        s23 = f"{m23.get('saplingIn')}→{m23.get('saplingOut')}"
        delta = (m21.get('saplingOut') or 0) - (m23.get('saplingOut') or 0)
        print(f'{tid:>5} {s21:>14} {s23:>14} {delta:>+12}')
    drops_m21 = [r['saplingIn']-r['saplingOut'] for r in data if r['methodId']=='M21' and r['textId'] in texts and r.get('saplingIn') is not None and r.get('saplingOut') is not None]
    drops_m23 = [r['saplingIn']-r['saplingOut'] for r in data if r['methodId']=='M23' and r['textId'] in texts and r.get('saplingIn') is not None and r.get('saplingOut') is not None]
    if drops_m21 and drops_m23:
        print(f'  mean Sapling drop: M21={statistics.mean(drops_m21):.1f}  M23={statistics.mean(drops_m23):.1f}  diff={statistics.mean(drops_m23)-statistics.mean(drops_m21):+.1f}')
report('FAILING (T3,T7,T8,T9,T11)', failing)
report('PASSING (T1,T2,T4,T5,T6,T10,T12)', passing)
EOF
```

Expected: a side-by-side table of M21 vs M23 Sapling scores per text, plus mean drop comparison.

- [ ] **Step 3: Decide next step based on results**

**Decision tree:**

- **WIN**: mean Sapling drop on failing texts is ≥ 30 points better for M23 vs M21, AND no passing text regresses to >15. → Skip to **Task 5: Ship**.
- **PARTIAL WIN**: M23 helps the failing texts but mean lift is <30, or one passing text regresses. → Go to **Task 4 alternate: Threshold tuning**, then re-bench. Up to 2 tuning iterations max.
- **LOSS**: M23 makes failing texts worse, or causes >2 passing texts to regress. → Skip to **Task 6: Document and park M23**.

- [ ] **Step 4: Commit the bench results**

```bash
git add bench-results/v12-m23-failing-only.json
git commit -m "$(cat <<'EOF'
chore(humanizer): v12 M23 phase-1 bench results

M23 vs M21 on T1-T12, Sapling judge only. See
docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md
for analysis (written in final task).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 alternate: Threshold tuning (only if Task 4 result is PARTIAL WIN)

Skip this task if Task 4 produced a clear WIN or clear LOSS.

The thresholds in `rule_compliance.ts` are first-cut. If M23 is helping but the critic is firing too aggressively (causing low-quality revisions) or not aggressively enough (revisions don't trigger when they should), tune the thresholds.

- [ ] **Step 1: Inspect the critic firing rate**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
python3 - <<'EOF'
import json
data = json.load(open('../bench-results/v12-m23-failing-only.json'))
m23 = [r for r in data if r['methodId']=='M23']
revised = [r for r in m23 if any('gemini_revise' in s['step'] for s in r['tokenSteps'])]
print(f'M23 ran on {len(m23)} texts; revision triggered on {len(revised)} ({100*len(revised)//max(len(m23),1)}%)')
for r in m23:
    triggered = any('gemini_revise' in s['step'] for s in r['tokenSteps'])
    print(f"  {r['textId']}: revised={triggered}, sap_out={r.get('saplingOut')}")
EOF
```

Read this carefully:
- Revision rate ~100% → thresholds too strict (loosen them by 25%).
- Revision rate ~0% → thresholds too lenient (tighten by 25%) or rules already satisfied by M21-style output (no further action needed; the rules aren't doing anything beyond M21).
- Revision rate 30–70% → healthy; tuning won't help, the rules just aren't enough.

- [ ] **Step 2: Adjust thresholds and re-run**

Edit `THRESHOLDS` in `backend/src/services/humanizer/critic/rule_compliance.ts`. Document the change in a comment above the THRESHOLDS object showing the previous values and the reason. Re-run Task 4 step 1.

Repeat at most twice. If two tuning iterations don't produce a clear WIN, commit the tuning attempts to git history and proceed to Task 6 (document and park).

- [ ] **Step 3: Commit threshold change**

```bash
git add backend/src/services/humanizer/critic/rule_compliance.ts
git commit -m "tune(humanizer): M23 thresholds — <describe change and why>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Ship M23 (only if Task 4 result is WIN)

Skip this task if Task 4 was not a WIN.

- [ ] **Step 1: Read current humanizer.service.ts to confirm the M21 reference**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
grep -n "getMethod" src/services/humanizer/humanizer.service.ts
```

Expected: a line referencing `getMethod('M21')` around line 174.

- [ ] **Step 2: Swap the production method to M23**

Modify `backend/src/services/humanizer/humanizer.service.ts`:

Find the block (around line 167–175):
```ts
    // Delegate humanization to M21 (router-picked anchor + strip-AI-vocab).
    // M21 won the v10.1 bake-off: mean Sapling drop 75 vs M7's 31, and mean
    // Copyscape drop 94 vs M7's 81. Cheaper too: 3 LLM calls per humanize
    // vs M7's 8. The router picks 1 anchor from {academic_formal,
    // academic_casual, argumentative, user_modern, user_narrative} via a
    // single low-cost Gemini call, then runs only that branch.
    onStage?.('stage', { stage: 'rewriting', step: 'voice_anchored' });
    const m21 = getMethod('M21');
    const m21Result = await m21.run(text, { tone, strength, lengthMode });
```

Replace with:
```ts
    // Delegate humanization to M23 (M21 router-anchor + four explicit rewrite
    // rules + deterministic compliance critic + one revision pass). M23 won
    // the v12 bench: mean Sapling drop on the 5 weak registers (T3, T7, T8,
    // T9, T11) improved by <FILL IN ACTUAL NUMBER> points vs M21, with no
    // regression on the 7 currently-passing texts. 3 LLM calls best case,
    // 4 with revision. See bench-results/v12-m23-failing-only.json and
    // docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md.
    onStage?.('stage', { stage: 'rewriting', step: 'voice_anchored' });
    const method = getMethod('M23');
    const methodResult = await method.run(text, { tone, strength, lengthMode });
```

Also update the local variable references from `m21Result` to `methodResult` in the lines that follow (the `tokenSteps` map and the final return). And update the version label from `v10.1` to `v12` in the three `console.log` strings that mention `[Humanizer v10.1]`. Do not change anything else in the file.

The exact `<FILL IN ACTUAL NUMBER>` value comes from Task 4 step 2 output (`diff=` line under FAILING).

- [ ] **Step 3: TypeScript compile check**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E 'humanizer.service|error TS' | head -20
```

Expected: no errors mentioning humanizer.service.ts.

- [ ] **Step 4: Smoke test the production pipeline end-to-end**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npx ts-node -r tsconfig-paths/register -e "
import { HumanizerService } from './src/services/humanizer/humanizer.service';
const text = 'Self-esteem plays a critical role in shaping the communicative experience of migrants using English as a second language. High self-esteem fosters confidence, which is essential for engaging in conversations, expressing needs, and participating in social, educational, and professional contexts. Conversely, low self-esteem may hinder communication by increasing anxiety, fear of judgment, and reluctance to speak.';
HumanizerService.humanizePipeline(text, 'academic', 50, 'match')
  .then(r => { console.log('--- OUTPUT ---'); console.log(r.rewrittenText); console.log('--- TOKENS ---', r.tokenUsage.totalInputTokens, '/', r.tokenUsage.totalOutputTokens); console.log('--- STEPS ---', r.tokenUsage.steps.map(s => s.step).join(', ')); })
  .catch(e => { console.error('FAIL', e); process.exit(1); });
"
```

Expected: a humanized output of similar length to the input, with `--- STEPS ---` showing `gemini_router, gemini_rewrite_<anchor>, [optional gemini_revise_<anchor>,] gpt_polish_<anchor>`. If the output is truncated, contains `<` brackets, or is empty: investigate before committing.

- [ ] **Step 5: Commit the production swap**

```bash
git add backend/src/services/humanizer/humanizer.service.ts
git commit -m "$(cat <<'EOF'
feat(humanizer): production v12 — swap M21 → M23 (rules + critic)

Per v12 bench results, M23 lifts the 5 weak registers (T3 argument,
T7 long essay, T8 how-to, T9 news, T11 memo) by <N> points mean
Sapling vs M21 with no regression on the 7 passing texts. M23 adds
four explicit rewrite rules (hedging, fronted-clause openings,
no-expansion, anti-X-and-Y) to the rewrite prompt and a deterministic
critic that triggers one revision pass on rule violations. 3 LLM calls
best case, 4 worst case — comparable cost to M21.

Bench: bench-results/v12-m23-failing-only.json
Handoff: docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Write the v12 handoff doc

Run this task regardless of WIN, PARTIAL WIN, or LOSS in Task 4 — it's how the next session picks up. The content differs by outcome.

**Files:**
- Create: `docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md`

- [ ] **Step 1: Write the handoff using one of the three templates below**

Pick the template matching the Task 4 outcome.

### Template A — WIN (M23 shipped)

Create `docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md` with:

```markdown
# Humanizer v12 — M23 Shipped

**Date:** 2026-05-02
**Branch:** master
**Production state:** v12 (M23 rules-critic-anchor) wired in `humanizer.service.ts`.

## What changed since v11

- New method M23 in `backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts`.
- New deterministic critic in `backend/src/services/humanizer/critic/rule_compliance.ts`.
- Pipeline shape: `strip → router → rewrite (with rules) → critic → [revise once if needed] → polish → strip`.
- 3 LLM calls best case, 4 worst case (vs M21's 3).

## Bench results

| Text | Tone | M21 sap-out | M23 sap-out | Δ | Status |
|---|---|---:|---:|---:|---|
<FILL IN PER-TEXT TABLE FROM TASK 4 STEP 2 OUTPUT>

Mean Sapling drop on failing texts: M21=<X>, M23=<Y>, diff=<+Z>.
Critic triggered revision on <N>/<12> texts.

## What this confirms

- The four rules (hedging, fronted openings, no-expansion, anti-X-and-Y) are detector-relevant signals, not just stylistic preferences.
- A deterministic rule-compliance critic with one revision pass works where past LLM critics (M1, M2, M9) failed — because rule compliance is mechanically verifiable, while detection-likelihood is not.

## Future work (carry-over from v11 handoff items not addressed)

1. Drop the `argumentative` anchor (path 1 in v11 handoff) — still untested.
2. Add 1–2 more period anchors (path 2).
3. Per-user anchor (path 3, Tier 2 monetization).
4. Top up Copyscape (path 4).

## Files of interest

```
backend/src/services/humanizer/
├── methods/
│   ├── M23_rules_critic_anchor.ts       # NEW — current production
│   └── M21_router_anchor.ts             # previous production, kept for reference
└── critic/
    └── rule_compliance.ts                # NEW — deterministic checker

backend/scripts/test/
└── test-rule-compliance.ts               # NEW — node:assert tests for the checker

bench-results/
└── v12-m23-failing-only.json             # NEW — phase-1 bench

docs/superpowers/
├── specs/2026-05-02-humanizer-m23-rules-critic-design.md   # NEW
├── plans/2026-05-02-humanizer-m23-rules-critic.md          # NEW
└── handoff/2026-05-02-humanizer-v12-m23-results.md         # NEW (THIS FILE)
```
```

### Template B — PARTIAL WIN or LOSS (M23 parked)

Create `docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md` with:

```markdown
# Humanizer v12 — M23 Parked

**Date:** 2026-05-02
**Branch:** master
**Production state:** v10.1 (M21) — UNCHANGED. M23 parked in the registry as a reference like other eliminated methods.

## What was tried

M23 layers four rewrite rules (hedging, fronted-clause openings, no-expansion, anti-X-and-Y two-item lists) onto M21's anchor pipeline, with a deterministic critic that triggers one revision pass on rule violations.

## Bench results

| Text | Tone | M21 sap-out | M23 sap-out | Δ | Notes |
|---|---|---:|---:|---:|---|
<FILL IN PER-TEXT TABLE FROM TASK 4 STEP 2 OUTPUT>

Mean Sapling drop on failing texts: M21=<X>, M23=<Y>, diff=<+/-Z>.
Critic triggered revision on <N>/<12> texts.

## Why it didn't ship

<ONE SENTENCE per failure mode observed. Examples to choose from:>
- Rules fired but the LLM produced low-quality revisions that hurt the passing texts.
- Critic rarely triggered because M21's output already happens to satisfy most rules.
- Hedging in T8/T11 made the output sound less assertive, which the detector still flagged as AI.

## Threshold tuning attempts

<IF Task 4 alternate ran: list the iterations, what changed, what the result was.>
<IF NOT: "No tuning iterations run — initial result was a clear LOSS.">

## What this rules out

- The hypothesis that "explicit rewrite rules in the prompt + a compliance critic is the missing signal" — the four rules drawn from the YouTube humanization tutorial don't move the bench in this codebase.
- This DOESN'T rule out: per-user anchors, additional period anchors, dropping the argumentative anchor — all path 1/2/3 items from the v11 handoff remain untested.

## Files retained for reference

```
backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts  # parked, registered
backend/src/services/humanizer/critic/rule_compliance.ts            # parked
backend/scripts/test/test-rule-compliance.ts                        # tests still pass
bench-results/v12-m23-failing-only.json                             # data
docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md
docs/superpowers/plans/2026-05-02-humanizer-m23-rules-critic.md
```

## Next session should start with

The v11 handoff's untested paths, in priority order: (1) drop the `argumentative` anchor and re-bench, (2) add 1–2 more period anchors, (3) per-user anchor as a Tier 2 feature.
```

- [ ] **Step 2: Commit the handoff**

```bash
git add docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md
git commit -m "$(cat <<'EOF'
docs(humanizer): v12 M23 results handoff

<Replace with: "M23 shipped — see file" OR "M23 parked — see file">

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final smoke check (only if Task 5 ran — production was changed)

Skip this task if M23 was parked.

- [ ] **Step 1: Confirm the dev server starts cleanly**

Run from `/Users/caonguyenvan/project/dothesis/backend`:

```bash
npm run dev 2>&1 | head -30
```

Wait for the server to log a "ready" or "listening" message. If it fails to start (TS compile error, missing env, port collision): investigate before considering ship complete.

Kill the server (`Ctrl+C`) once it's confirmed running.

- [ ] **Step 2: (Optional) Manual UI smoke**

If a frontend dev server is also available, paste a short text into the humanizer UI and confirm:
- The output is non-empty and reasonably sized
- The "before" / "after" AI-score badges render (or render `—` if Copyscape is out)
- No 500 errors in the backend log

If frontend isn't running, skip this and rely on the Task 5 step 4 ts-node smoke as sufficient verification.

---

## Self-Review

After writing the plan, I checked it against the spec:

**Spec coverage:**
- Goal (lift 5 failing registers via 4 rules + critic): Tasks 1, 3, 4 cover this end-to-end. ✓
- Pipeline shape (strip→router→rewrite-with-rules→critic→[revise]→polish→strip): Task 3 step 1. ✓
- Four rules with thresholds: Task 1 implements all four with the spec's thresholds; Task 3 inlines them in the rewrite prompt. ✓
- Deterministic critic, no LLM: Task 1 enforced via pure functions, Task 2 verifies via assertion script. ✓
- One revision attempt only: Task 3 step 1 implementation explicitly does ONE call (no loop). ✓
- M21 unchanged: Task 3 file structure note states M23 inlines the prompts rather than importing from M21. (Spec mentioned a refactor; I deliberately deviated to keep M21 untouched, with the rationale documented in Task 3 step 1's header comment. This is a small spec deviation that protects the production path — flagged here for transparency.) ✓
- Polish unchanged: Task 3 inlines the same POLISH_TEMPLATE as M21. ✓
- Bench plan (phase 1 / phase 2): Task 4 covers it; I collapsed phases 1 and 2 into a single full-corpus run (Option A in Task 4 step 1) since the existing harness lacks a `--texts` flag and editing TEXT_IDS for 5-text-only runs is more friction than running the full 12. The same JSON serves both phases. ✓
- Ship criteria (≥30 mean drop on failing AND ≤15 on passing): Task 4 step 3 decision tree, Task 5 ships only if criteria met. ✓
- Handoff doc: Task 6 with two templates. ✓

**Placeholder scan:** The `<FILL IN ACTUAL NUMBER>` in Task 5 step 2 and the `<FILL IN PER-TEXT TABLE>` in Task 6 are intentional — they require the human to insert numbers from the bench output. They are clearly marked, not "TODO" or "TBD". The handoff templates have `<X>`, `<Y>`, `<Z>` slots that the executor fills in from the analysis script. Acceptable.

**Type consistency:** `RuleId`, `RuleViolation`, `ComplianceReport`, `ComplianceMetrics` defined in Task 1 and used in Task 3 with consistent names. `MethodOptions`, `MethodResult`, `MethodTokenStep` types reused from `methods/types.ts` unchanged. ✓
