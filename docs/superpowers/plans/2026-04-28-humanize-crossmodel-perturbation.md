# Humanizer v7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the iterative critic-based pipeline with a linear cross-model chain interleaved with non-LLM programmatic perturbations to bypass GPTZero 4.4b.

**Architecture:** Three LLM stages (Gemini rewrite → GPT cross-rewrite → Gemini polish) with two programmatic perturbation layers between them. Perturbations apply 6 deterministic/random operations (synonym swap, contraction toggle, human marker injection, sentence splitting, punctuation variation, starter variation) at the sentence level, language-aware (EN + VI).

**Tech Stack:** TypeScript, Node.js (no Jest — uses ts-node test scripts following the existing `score-samples.ts` pattern). Models: `gemini-3-flash-preview`, `gpt-5.5`. Existing services: `GeminiService`, `OpenAIService` from `@/services/ai/`.

**Reference:** Spec at `docs/superpowers/specs/2026-04-28-humanize-crossmodel-perturbation-design.md`

---

## File Structure

**New directory layout:**
```
backend/src/services/humanizer/
  ├── humanizer.service.ts           # Main pipeline (refactored — linear, no loop)
  ├── perturbation/
  │   ├── perturbation.engine.ts     # Orchestrator class
  │   ├── operations.ts              # 6 perturbation operation functions
  │   ├── synonym.dictionary.ts      # EN + VI synonym maps
  │   └── human-markers.ts           # Filler word lists EN + VI
  └── prompts/
      ├── rewrite.prompt.ts          # Stage 1 prompt builder (Gemini)
      ├── cross-rewrite.prompt.ts    # Stage 2 prompt builder (GPT)
      └── polish.prompt.ts           # Stage 3 prompt builder (Gemini)

backend/src/scripts/
  ├── test-perturbation.ts           # NEW: assertion test for perturbation engine
  └── test-humanize-pipeline.ts      # NEW: end-to-end pipeline manual test
```

**Files to delete:** `backend/src/services/humanizer.service.ts` (moved into new directory).

**Files to update:**
- `backend/src/api/routes/humanize.ts` — import path only
- `backend/src/api/routes/admin/humanize.ts` — import path only (if it imports the service)

---

## Task 1: Set up new directory structure and move existing service

**Files:**
- Create: `backend/src/services/humanizer/` (directory)
- Create: `backend/src/services/humanizer/perturbation/` (directory)
- Create: `backend/src/services/humanizer/prompts/` (directory)
- Move: `backend/src/services/humanizer.service.ts` → `backend/src/services/humanizer/humanizer.service.ts`
- Modify: any file importing from `@/services/humanizer.service`

- [ ] **Step 1: Create directories**

```bash
cd /Users/caonguyenvan/project/dothesis/backend
mkdir -p src/services/humanizer/perturbation src/services/humanizer/prompts
```

- [ ] **Step 2: Move the existing service file**

```bash
git mv src/services/humanizer.service.ts src/services/humanizer/humanizer.service.ts
```

- [ ] **Step 3: Find all importers of the old path**

Use Grep tool with pattern `from ['"]@/services/humanizer\.service['"]` across `backend/src/`.
Expected: at least `backend/src/api/routes/humanize.ts` and possibly `backend/src/api/routes/admin/humanize.ts`.

- [ ] **Step 4: Update each importer**

Change every occurrence of:
```typescript
from '@/services/humanizer.service'
```
to:
```typescript
from '@/services/humanizer/humanizer.service'
```

- [ ] **Step 5: Verify TypeScript still compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(humanize): move service into humanizer/ directory

Prepare for v7 cross-model + perturbation pipeline. No behavior change."
```

---

## Task 2: Create English synonym dictionary

**Files:**
- Create: `backend/src/services/humanizer/perturbation/synonym.dictionary.ts`

- [ ] **Step 1: Write the dictionary file**

```typescript
// backend/src/services/humanizer/perturbation/synonym.dictionary.ts

// Decision: Built-in synonym dictionary instead of external API (Datamuse, WordsAPI).
// External APIs add latency, cost, and rate limits. The ~150 most common LLM-overused
// words cover the highest-impact substitutions. Each entry maps to 2-4 less predictable
// alternatives that LLMs are statistically less likely to choose.

export type SynonymMap = Record<string, string[]>;

export const SYNONYMS_EN: SynonymMap = {
  // Overused LLM verbs
  'demonstrate': ['show', 'prove', 'reveal', 'lay bare'],
  'demonstrates': ['shows', 'proves', 'reveals', 'lays bare'],
  'utilize': ['use', 'rely on', 'lean on'],
  'utilizes': ['uses', 'relies on', 'leans on'],
  'illustrate': ['show', 'spell out', 'paint'],
  'highlight': ['point to', 'flag', 'spotlight'],
  'highlights': ['points to', 'flags', 'spotlights'],
  'indicate': ['suggest', 'point to', 'hint at'],
  'indicates': ['suggests', 'points to', 'hints at'],
  'suggest': ['hint', 'imply', 'point to'],
  'suggests': ['hints', 'implies', 'points to'],
  'reveal': ['show', 'expose', 'lay bare'],
  'reveals': ['shows', 'exposes', 'lays bare'],
  'enable': ['let', 'allow', 'open the door for'],
  'enables': ['lets', 'allows', 'opens the door for'],
  'achieve': ['hit', 'pull off', 'land'],
  'achieves': ['hits', 'pulls off', 'lands'],
  'address': ['tackle', 'handle', 'deal with'],
  'addresses': ['tackles', 'handles', 'deals with'],
  'establish': ['set up', 'build', 'lay down'],
  'examine': ['look at', 'dig into', 'pick apart'],
  'explore': ['dig into', 'poke at', 'wander through'],
  'observe': ['notice', 'spot', 'catch'],
  'consider': ['think about', 'weigh', 'mull'],
  'develop': ['build', 'put together', 'grow'],
  'enhance': ['boost', 'sharpen', 'lift'],
  'improve': ['boost', 'sharpen', 'tune up'],
  'increase': ['bump up', 'push up', 'climb'],
  'decrease': ['drop', 'shrink', 'fall'],
  'impact': ['hit', 'shake up', 'shape'],
  'transform': ['reshape', 'flip', 'overhaul'],
  'transforms': ['reshapes', 'flips', 'overhauls'],

  // Overused LLM adjectives
  'important': ['key', 'central', 'big', 'real'],
  'significant': ['real', 'serious', 'big', 'meaningful'],
  'substantial': ['real', 'sizable', 'hefty'],
  'considerable': ['real', 'sizable', 'fair-sized'],
  'remarkable': ['striking', 'wild', 'standout'],
  'effective': ['solid', 'workable', 'sharp'],
  'efficient': ['lean', 'tight', 'snappy'],
  'comprehensive': ['full', 'sweeping', 'broad'],
  'extensive': ['wide', 'sprawling', 'deep'],
  'numerous': ['plenty of', 'a lot of', 'no shortage of'],
  'various': ['all sorts of', 'a mix of', 'different'],
  'multiple': ['several', 'a bunch of', 'a stack of'],
  'essential': ['core', 'must-have', 'basic'],
  'critical': ['core', 'make-or-break', 'key'],
  'crucial': ['key', 'make-or-break', 'core'],
  'fundamental': ['basic', 'core', 'bedrock'],
  'innovative': ['fresh', 'new', 'unconventional'],
  'advanced': ['modern', 'cutting', 'newer'],
  'sophisticated': ['polished', 'sharp', 'refined'],
  'complex': ['tangled', 'knotty', 'layered'],
  'simple': ['plain', 'bare', 'no-frills'],
  'difficult': ['tough', 'hard', 'thorny'],
  'challenging': ['tough', 'rough', 'sticky'],
  'meaningful': ['real', 'solid', 'worthwhile'],
  'valuable': ['worth it', 'real', 'useful'],
  'beneficial': ['useful', 'a plus', 'handy'],

  // Overused LLM nouns
  'aspect': ['side', 'piece', 'angle'],
  'aspects': ['sides', 'pieces', 'angles'],
  'factor': ['piece', 'driver', 'element'],
  'factors': ['pieces', 'drivers', 'elements'],
  'element': ['piece', 'bit', 'part'],
  'elements': ['pieces', 'bits', 'parts'],
  'approach': ['way', 'angle', 'route'],
  'method': ['way', 'route', 'approach'],
  'process': ['flow', 'routine', 'cycle'],
  'system': ['setup', 'rig', 'machine'],
  'framework': ['scaffold', 'frame', 'shell'],
  'concept': ['idea', 'notion', 'angle'],
  'principle': ['rule', 'tenet', 'axiom'],
  'capability': ['ability', 'chops', 'reach'],
  'opportunity': ['chance', 'opening', 'shot'],
  'challenge': ['hurdle', 'snag', 'wall'],
  'solution': ['fix', 'answer', 'workaround'],
  'outcome': ['result', 'payoff', 'upshot'],
  'outcomes': ['results', 'payoffs', 'upshots'],
  'benefit': ['plus', 'win', 'upside'],
  'benefits': ['pluses', 'wins', 'upsides'],
  'advantage': ['edge', 'leg up', 'plus'],
  'implementation': ['rollout', 'execution', 'build-out'],
  'integration': ['hookup', 'tie-in', 'merge'],
  'optimization': ['tuning', 'tightening', 'sharpening'],

  // Overused LLM adverbs
  'particularly': ['especially', 'above all', 'most of all'],
  'specifically': ['namely', 'precisely', 'in particular'],
  'effectively': ['in practice', 'really', 'in effect'],
  'efficiently': ['cleanly', 'tightly', 'leanly'],
  'significantly': ['noticeably', 'a lot', 'sharply'],
  'substantially': ['a lot', 'noticeably', 'sharply'],
  'considerably': ['a lot', 'sharply', 'plenty'],
  'increasingly': ['more and more', 'growingly', 'steadily more'],
  'consequently': ['so', 'as a result', 'which means'],
  'additionally': ['also', 'plus', 'on top of that'],
  'furthermore': ['also', 'plus', 'on top of that'],
  'moreover': ['also', 'plus', 'on top of that'],
};

// Decision: Vietnamese synonyms focus on common AI-overused academic words.
// Vietnamese has fewer "AI tells" than English but words like "đóng vai trò", "góp phần",
// "mang tính chất" appear in nearly every LLM-generated Vietnamese text.
export const SYNONYMS_VI: SynonymMap = {
  'quan trọng': ['then chốt', 'cốt lõi', 'lớn'],
  'đáng kể': ['rõ rệt', 'nổi bật', 'không nhỏ'],
  'hiệu quả': ['ổn', 'gọn', 'tốt'],
  'phát triển': ['lớn lên', 'mở rộng', 'tăng trưởng'],
  'cải thiện': ['nâng cao', 'làm tốt hơn', 'siết lại'],
  'thể hiện': ['cho thấy', 'lộ ra', 'phơi bày'],
  'cho thấy': ['lộ ra', 'chỉ ra', 'phơi bày'],
  'thực hiện': ['làm', 'tiến hành', 'triển khai'],
  'mang lại': ['đem lại', 'tạo ra', 'cho ra'],
  'đóng vai trò': ['giữ vai trò', 'đảm nhận', 'gánh vác'],
  'góp phần': ['giúp', 'thêm vào', 'cộng vào'],
  'tạo điều kiện': ['mở đường', 'cho phép', 'giúp'],
  'đảm bảo': ['giữ chắc', 'bảo đảm', 'lo cho'],
  'tăng cường': ['siết chặt', 'củng cố', 'đẩy mạnh'],
  'phù hợp': ['hợp', 'ăn khớp', 'khớp'],
  'cần thiết': ['cần', 'phải có', 'không thể thiếu'],
  'hỗ trợ': ['giúp', 'tiếp sức', 'chống lưng'],
  'phương pháp': ['cách', 'lối', 'kiểu'],
  'phương thức': ['cách', 'lối', 'kiểu'],
  'yếu tố': ['mảnh', 'phần', 'điểm'],
  'khía cạnh': ['mặt', 'góc', 'phía'],
  'vấn đề': ['chuyện', 'điểm', 'việc'],
  'lợi ích': ['cái lợi', 'điểm cộng', 'cái được'],
  'khả năng': ['sức', 'tầm', 'mức'],
  'cơ hội': ['dịp', 'cửa', 'cơ may'],
  'thách thức': ['khó khăn', 'rào cản', 'cửa ải'],
  'đặc biệt': ['nhất là', 'trên hết', 'hơn cả'],
  'rõ ràng': ['thấy rõ', 'minh bạch', 'tỏ tường'],
  'do đó': ['nên', 'vì thế', 'thành ra'],
  'tuy nhiên': ['nhưng mà', 'có điều', 'song'],
  'ngoài ra': ['thêm nữa', 'còn nữa', 'với lại'],
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/perturbation/synonym.dictionary.ts
git commit -m "feat(humanize): add EN+VI synonym dictionary for perturbation engine"
```

---

## Task 3: Create human markers list

**Files:**
- Create: `backend/src/services/humanizer/perturbation/human-markers.ts`

- [ ] **Step 1: Write the markers file**

```typescript
// backend/src/services/humanizer/perturbation/human-markers.ts

// Decision: Sentence-start fillers that humans use in writing but LLMs almost never
// produce naturally in academic/formal text. Injecting these at the start of a small
// percentage of sentences mimics natural human prose rhythm.

export const SENTENCE_STARTERS_EN: string[] = [
  'Honestly, ',
  'Look, ',
  'I mean, ',
  'Actually, ',
  'Frankly, ',
  'Truthfully, ',
  'In reality, ',
  'To be fair, ',
  'Granted, ',
  'Sure, ',
];

export const SENTENCE_STARTERS_VI: string[] = [
  'Thực ra, ',
  'Nói thật, ',
  'Thẳng thắn mà nói, ',
  'Theo mình, ',
  'Nhìn chung, ',
  'Có điều, ',
  'Thật ra, ',
  'Phải công nhận, ',
];

// Decision: Conjunction starters (And, But, So) at the start of sentences are
// considered ungrammatical in academic writing — which is why LLMs avoid them.
// Humans do this constantly. Each is a strong signal of human authorship.
export const CONJUNCTION_STARTERS_EN: string[] = [
  'And ',
  'But ',
  'So ',
  'Still, ',
  'Yet ',
  'Plus, ',
];

export const CONJUNCTION_STARTERS_VI: string[] = [
  'Mà ',
  'Nhưng ',
  'Còn ',
  'Vậy nên ',
  'Thế nhưng ',
];

// Decision: Common English contractions. Maps non-contracted form → contracted form.
// LLMs are inconsistent about contractions in formal text — toggling some toward
// contractions and others away matches the natural human inconsistency.
export const CONTRACTIONS_EN: Record<string, string> = {
  'it is': "it's",
  'it has': "it's",
  'do not': "don't",
  'does not': "doesn't",
  'did not': "didn't",
  'is not': "isn't",
  'are not': "aren't",
  'was not': "wasn't",
  'were not': "weren't",
  'will not': "won't",
  'would not': "wouldn't",
  'could not': "couldn't",
  'should not': "shouldn't",
  'cannot': "can't",
  'can not': "can't",
  'have not': "haven't",
  'has not': "hasn't",
  'had not': "hadn't",
  'they are': "they're",
  'they have': "they've",
  'we are': "we're",
  'we have': "we've",
  'you are': "you're",
  'you have': "you've",
  'I am': "I'm",
  'I have': "I've",
  'that is': "that's",
  'there is': "there's",
  'what is': "what's",
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/perturbation/human-markers.ts
git commit -m "feat(humanize): add EN+VI human marker word lists for perturbation"
```

---

## Task 4: Implement the 6 perturbation operations

**Files:**
- Create: `backend/src/services/humanizer/perturbation/operations.ts`

- [ ] **Step 1: Write all 6 operation functions**

```typescript
// backend/src/services/humanizer/perturbation/operations.ts

// Decision: Each operation is a pure function — given the same sentence, lang, and rng
// output, it produces the same output. This makes the engine deterministic for testing
// when given a seeded RNG, while still random in production with Math.random.

import { SYNONYMS_EN, SYNONYMS_VI, SynonymMap } from './synonym.dictionary';
import {
  SENTENCE_STARTERS_EN,
  SENTENCE_STARTERS_VI,
  CONJUNCTION_STARTERS_EN,
  CONJUNCTION_STARTERS_VI,
  CONTRACTIONS_EN,
} from './human-markers';

export type Lang = 'en' | 'vi';
export type RNG = () => number;
export type PerturbationOp = (sentence: string, lang: Lang, rng: RNG) => string;

function pick<T>(arr: T[], rng: RNG): T {
  return arr[Math.floor(rng() * arr.length)];
}

// Op 1: Synonym swap — pick one matching word in the sentence and replace with a synonym
export const synonymSwap: PerturbationOp = (sentence, lang, rng) => {
  const dict: SynonymMap = lang === 'vi' ? SYNONYMS_VI : SYNONYMS_EN;
  const lower = sentence.toLowerCase();
  const candidates: Array<{ word: string; alternatives: string[] }> = [];

  for (const word of Object.keys(dict)) {
    if (lower.includes(word)) {
      candidates.push({ word, alternatives: dict[word] });
    }
  }

  if (candidates.length === 0) return sentence;
  const chosen = pick(candidates, rng);
  const replacement = pick(chosen.alternatives, rng);

  // Case-insensitive replace, preserve original casing of first letter if it was capitalized
  const regex = new RegExp(`\\b${chosen.word}\\b`, 'i');
  return sentence.replace(regex, (match) => {
    if (match[0] === match[0].toUpperCase()) {
      return replacement[0].toUpperCase() + replacement.slice(1);
    }
    return replacement;
  });
};

// Op 2: Contraction toggle — find a contractable phrase and contract it (EN only)
export const toggleContraction: PerturbationOp = (sentence, lang, rng) => {
  if (lang !== 'en') return sentence;
  const lower = sentence.toLowerCase();
  const candidates: Array<{ phrase: string; contracted: string }> = [];

  for (const [phrase, contracted] of Object.entries(CONTRACTIONS_EN)) {
    if (lower.includes(phrase)) {
      candidates.push({ phrase, contracted });
    }
  }

  if (candidates.length === 0) return sentence;
  const chosen = pick(candidates, rng);
  const regex = new RegExp(`\\b${chosen.phrase}\\b`, 'i');
  return sentence.replace(regex, (match) => {
    if (match[0] === match[0].toUpperCase()) {
      return chosen.contracted[0].toUpperCase() + chosen.contracted.slice(1);
    }
    return chosen.contracted;
  });
};

// Op 3: Human marker injection — prepend a filler phrase to the sentence
export const injectHumanMarker: PerturbationOp = (sentence, lang, rng) => {
  const markers = lang === 'vi' ? SENTENCE_STARTERS_VI : SENTENCE_STARTERS_EN;
  const marker = pick(markers, rng);
  // Lowercase the first letter of the original sentence since the marker ends with a comma+space
  const adjusted = sentence[0].toLowerCase() + sentence.slice(1);
  return marker + adjusted;
};

// Op 4: Sentence splitting — split on a comma into two sentences
export const splitSentence: PerturbationOp = (sentence, _lang, rng) => {
  // Find comma positions that are at least 4 words from start and 4 words from end
  const commaIndices: number[] = [];
  for (let i = 0; i < sentence.length; i++) {
    if (sentence[i] === ',') commaIndices.push(i);
  }
  if (commaIndices.length === 0) return sentence;

  // Pick a random comma to split on
  const splitIdx = pick(commaIndices, rng);
  const before = sentence.slice(0, splitIdx).trim();
  const after = sentence.slice(splitIdx + 1).trim();

  // Only split if both halves are at least 3 words
  if (before.split(/\s+/).length < 3 || after.split(/\s+/).length < 3) return sentence;

  // Capitalize the start of the second half
  const afterCapitalized = after[0].toUpperCase() + after.slice(1);
  return `${before}. ${afterCapitalized}`;
};

// Op 5: Punctuation variation — replace one period at the end of an internal clause with
// a semicolon or em dash, OR add an em dash for an aside.
export const varyPunctuation: PerturbationOp = (sentence, _lang, rng) => {
  // Find a comma to upgrade to em dash (more dramatic)
  const commaIndices: number[] = [];
  for (let i = 0; i < sentence.length; i++) {
    if (sentence[i] === ',') commaIndices.push(i);
  }
  if (commaIndices.length === 0) return sentence;

  const targetComma = pick(commaIndices, rng);
  const choice = rng();
  let replacement: string;
  if (choice < 0.5) replacement = ' —';
  else if (choice < 0.8) replacement = ';';
  else replacement = ' …';

  return sentence.slice(0, targetComma) + replacement + sentence.slice(targetComma + 1);
};

// Op 6: Starter variation — prepend a conjunction starter (And, But, So, etc.)
export const varyStarter: PerturbationOp = (sentence, lang, rng) => {
  const starters = lang === 'vi' ? CONJUNCTION_STARTERS_VI : CONJUNCTION_STARTERS_EN;
  const starter = pick(starters, rng);
  const adjusted = sentence[0].toLowerCase() + sentence.slice(1);
  return starter + adjusted;
};

export const ALL_OPERATIONS: PerturbationOp[] = [
  synonymSwap,
  toggleContraction,
  injectHumanMarker,
  splitSentence,
  varyPunctuation,
  varyStarter,
];
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/perturbation/operations.ts
git commit -m "feat(humanize): add 6 perturbation operations (synonym, contraction, etc.)"
```

---

## Task 5: Implement PerturbationEngine orchestrator

**Files:**
- Create: `backend/src/services/humanizer/perturbation/perturbation.engine.ts`

- [ ] **Step 1: Write the engine**

```typescript
// backend/src/services/humanizer/perturbation/perturbation.engine.ts

// Decision: PerturbationEngine is a static class with a single public method `perturb`.
// It splits text into sentences, decides per-sentence whether to perturb based on rate,
// picks 1-2 random operations per perturbed sentence, applies them, and reassembles.
// The rng parameter defaults to Math.random but can be overridden for deterministic tests.

import { ALL_OPERATIONS, Lang, RNG } from './operations';

// Reuse language detection from statistical detector — keeps both modules in sync.
function detectLanguage(text: string): Lang {
  const viPattern = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/gi;
  const viMatches = (text.match(viPattern) || []).length;
  return (viMatches / text.length) > 0.02 ? 'vi' : 'en';
}

// Sentence splitter — keeps the sentence-ending punctuation attached.
// Uses lookbehind to split on .!? followed by whitespace.
function splitIntoSentences(text: string): string[] {
  // Split keeping the punctuation. Match: word/non-punct chars then .!? then whitespace.
  const matches = text.match(/[^.!?]+[.!?]+(?:\s+|$)/g);
  if (!matches) return [text];
  return matches.map(s => s.trim()).filter(s => s.length > 0);
}

export class PerturbationEngine {
  // Decision: Rate scales with strength so users get more aggressive perturbation
  // when they ask for stronger humanization. The numbers (0.20, 0.35, 0.50) were
  // chosen so that even the lightest setting still produces visible non-LLM signal,
  // while the strongest setting stops short of making text obviously broken.
  static getRate(strength: number): number {
    if (strength <= 30) return 0.20;
    if (strength <= 70) return 0.35;
    return 0.50;
  }

  static perturb(text: string, strength: number, rng: RNG = Math.random): string {
    const lang = detectLanguage(text);
    const rate = this.getRate(strength);
    const sentences = splitIntoSentences(text);

    const result: string[] = [];

    for (const sentence of sentences) {
      // Decide whether to perturb this sentence
      if (rng() > rate) {
        result.push(sentence);
        continue;
      }

      // Pick 1 or 2 operations randomly (50/50 chance for 2 ops)
      const opCount = rng() < 0.5 ? 1 : 2;
      const chosenOps = this.pickRandomOps(opCount, rng);

      let perturbed = sentence;
      for (const op of chosenOps) {
        perturbed = op(perturbed, lang, rng);
      }
      result.push(perturbed);
    }

    return result.join(' ');
  }

  private static pickRandomOps(count: number, rng: RNG) {
    // Shuffle a copy of ALL_OPERATIONS and take the first `count`
    const shuffled = [...ALL_OPERATIONS];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled.slice(0, count);
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/perturbation/perturbation.engine.ts
git commit -m "feat(humanize): add PerturbationEngine orchestrator with rate-based scaling"
```

---

## Task 6: Write perturbation engine test script

**Files:**
- Create: `backend/src/scripts/test-perturbation.ts`

- [ ] **Step 1: Write the test script using Node's built-in assert**

```typescript
// backend/src/scripts/test-perturbation.ts

// Decision: Standalone assertion test script following the project's existing pattern
// (see score-samples.ts). No Jest/Mocha — runs via `npx ts-node`. Each test logs
// pass/fail with a descriptive message.

import * as assert from 'assert';
import { PerturbationEngine } from '@/services/humanizer/perturbation/perturbation.engine';
import {
  synonymSwap,
  toggleContraction,
  injectHumanMarker,
  splitSentence,
  varyPunctuation,
  varyStarter,
} from '@/services/humanizer/perturbation/operations';

// Seeded RNG for deterministic tests (mulberry32)
function seededRng(seed: number): () => number {
  return function () {
    seed |= 0;
    seed = (seed + 0x6D2B79F5) | 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err: any) {
    console.log(`  ✗ ${name}`);
    console.log(`      ${err.message}`);
    failed++;
  }
}

console.log('\n=== Perturbation Operations ===\n');

test('synonymSwap replaces a known word in EN', () => {
  const result = synonymSwap('This is an important finding.', 'en', seededRng(1));
  assert.notStrictEqual(result, 'This is an important finding.');
  assert.match(result, /This is an (key|central|big|real) finding\./);
});

test('synonymSwap returns input unchanged when no matches', () => {
  const result = synonymSwap('Quick fox jumps.', 'en', seededRng(1));
  assert.strictEqual(result, 'Quick fox jumps.');
});

test('synonymSwap preserves capitalization for sentence-start words', () => {
  const result = synonymSwap('Important findings emerged.', 'en', seededRng(1));
  assert.match(result, /^[A-Z]/);
});

test('toggleContraction contracts "do not" → "don\'t"', () => {
  const result = toggleContraction('We do not agree with the conclusion.', 'en', seededRng(1));
  assert.match(result, /don't/);
});

test('toggleContraction is a no-op for Vietnamese', () => {
  const input = 'Chúng tôi không đồng ý với kết luận.';
  const result = toggleContraction(input, 'vi', seededRng(1));
  assert.strictEqual(result, input);
});

test('injectHumanMarker prepends a filler phrase in EN', () => {
  const result = injectHumanMarker('The data is clear.', 'en', seededRng(1));
  assert.match(result, /^(Honestly|Look|I mean|Actually|Frankly|Truthfully|In reality|To be fair|Granted|Sure), /);
});

test('injectHumanMarker prepends a filler phrase in VI', () => {
  const result = injectHumanMarker('Dữ liệu rất rõ ràng.', 'vi', seededRng(1));
  assert.match(result, /^(Thực ra|Nói thật|Thẳng thắn mà nói|Theo mình|Nhìn chung|Có điều|Thật ra|Phải công nhận), /);
});

test('splitSentence splits at a comma into two sentences', () => {
  const input = 'The teacher walked into the room, and everyone went silent immediately.';
  const result = splitSentence(input, 'en', seededRng(1));
  assert.notStrictEqual(result, input);
  assert.ok(result.includes('. '), 'Expected a period+space mid-string');
});

test('splitSentence is a no-op when no commas present', () => {
  const input = 'This sentence has no commas.';
  const result = splitSentence(input, 'en', seededRng(1));
  assert.strictEqual(result, input);
});

test('varyPunctuation replaces a comma with em dash, semicolon, or ellipsis', () => {
  const input = 'The data, which was collected last year, shows growth.';
  const result = varyPunctuation(input, 'en', seededRng(1));
  assert.notStrictEqual(result, input);
  assert.ok(result.includes(' —') || result.includes(';') || result.includes(' …'));
});

test('varyStarter prepends And/But/So', () => {
  const result = varyStarter('The findings were unexpected.', 'en', seededRng(1));
  assert.match(result, /^(And |But |So |Still, |Yet |Plus, )/);
});

console.log('\n=== PerturbationEngine ===\n');

test('PerturbationEngine.getRate scales with strength', () => {
  assert.strictEqual(PerturbationEngine.getRate(20), 0.20);
  assert.strictEqual(PerturbationEngine.getRate(50), 0.35);
  assert.strictEqual(PerturbationEngine.getRate(80), 0.50);
});

test('PerturbationEngine.perturb produces different output from input (EN, strength 50)', () => {
  const input = 'The research demonstrates that machine learning is important. ' +
    'Significant findings emerged from the analysis. ' +
    'Furthermore, the results enable us to consider new approaches. ' +
    'It is important to note that these benefits are substantial.';
  const result = PerturbationEngine.perturb(input, 50, seededRng(42));
  assert.notStrictEqual(result, input, 'Output should differ from input');
});

test('PerturbationEngine.perturb produces different output from input (VI, strength 50)', () => {
  const input = 'Nghiên cứu thể hiện rằng học máy quan trọng. ' +
    'Yếu tố này đóng vai trò đáng kể trong phương pháp mới. ' +
    'Ngoài ra, kết quả cho thấy lợi ích rõ ràng cần thiết.';
  const result = PerturbationEngine.perturb(input, 50, seededRng(42));
  assert.notStrictEqual(result, input);
});

test('PerturbationEngine.perturb is deterministic with seeded rng', () => {
  const input = 'The research demonstrates important findings.';
  const a = PerturbationEngine.perturb(input, 50, seededRng(42));
  const b = PerturbationEngine.perturb(input, 50, seededRng(42));
  assert.strictEqual(a, b, 'Same seed should produce same output');
});

test('PerturbationEngine.perturb preserves text length within reasonable bounds', () => {
  const input = 'The research demonstrates that machine learning is important. ' +
    'Significant findings emerged from the analysis.';
  const result = PerturbationEngine.perturb(input, 50, seededRng(7));
  // Output should be within 50%-200% of input length
  assert.ok(result.length > input.length * 0.5, 'Output too short');
  assert.ok(result.length < input.length * 2.0, 'Output too long');
});

console.log(`\n=== Results: ${passed} passed, ${failed} failed ===\n`);
process.exit(failed === 0 ? 0 : 1);
```

- [ ] **Step 2: Run the test script and verify all pass**

Run: `cd backend && npx ts-node -r tsconfig-paths/register src/scripts/test-perturbation.ts`
Expected: All tests pass, exit code 0. Output ends with `=== Results: 16 passed, 0 failed ===`.

If any tests fail, fix the operations or engine to match the test expectations. Re-run until all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/src/scripts/test-perturbation.ts
git commit -m "test(humanize): add assertion tests for perturbation operations and engine"
```

---

## Task 7: Create the rewrite prompt builder (Stage 1)

**Files:**
- Create: `backend/src/services/humanizer/prompts/rewrite.prompt.ts`

- [ ] **Step 1: Write the prompt builder**

```typescript
// backend/src/services/humanizer/prompts/rewrite.prompt.ts

// Decision: Stage 1 prompt for Gemini. Focuses on creative restructuring (varied grammar,
// sensory language, anti-formulaic-flow). This is what the v6 prompt did, kept here
// because it remains useful as the first transformation pass — the perturbation layer
// adds non-LLM noise on top.

const TONE_INSTRUCTIONS: Record<string, string> = {
  academic:
    'You are a 28-year-old PhD candidate who genuinely cares about this topic. You write with confidence about what the evidence says. You make strong claims: "The data is unambiguous." Sometimes your sentences get long because you\'re excited about an idea, sometimes you cut yourself short. You start sentences with "What the data actually shows is..." or invert word order ("Rarely do we see...", "Not once in the dataset..."). You mix technical analysis with concrete examples — describe what improvements looked like in the lab, not just that they happened.',
  casual:
    'You are a smart college senior explaining this topic to a classmate over coffee. You\'re confident and direct: "Yeah, it\'s a big deal." You interrupt yourself with asides in dashes or parentheses, and you ground abstract ideas with concrete images ("picture a teacher at midnight, still grading"). You never chain clauses with ", and" — use a dash, semicolon, or new sentence instead.',
  persuasive:
    'You are an experienced journalist writing an opinion piece. You commit to your point of view: "This policy failed." Your writing has rhythm — long, clause-heavy sentences then a short one. Stop dead. Then pick up. You lead paragraphs with provocative claims, not qualifications. You use concrete imagery instead of abstractions. You sometimes invert word order: "Gone are the days when..."',
};

const LENGTH_INSTRUCTIONS: Record<string, string> = {
  match: 'Keep the output approximately the same length as the input.',
  shorter: 'Make the output about 15% shorter than the input. Be more concise.',
  longer: 'Make the output about 15% longer. Add more detail and elaboration.',
};

export function buildRewritePrompt(tone: string, strength: number, lengthMode: string): string {
  const toneInstr = TONE_INSTRUCTIONS[tone] || TONE_INSTRUCTIONS.academic;
  const lengthInstr = LENGTH_INSTRUCTIONS[lengthMode] || LENGTH_INSTRUCTIONS.match;

  const strengthDesc =
    strength <= 30
      ? 'Make LIGHT edits. Fix the most obvious AI-sounding phrases, add some sentence length variation, and remove blatant AI transitions.'
      : strength <= 70
        ? 'Make SUBSTANTIAL edits. You MUST restructure sentences. Split long sentences into short+long pairs. Merge short sentences. Replace AI transitions with natural flow. Every sentence should read noticeably different from the original.'
        : 'Do a COMPLETE rewrite. Rewrite every sentence from scratch as if you were a human expert writing about this topic for the first time.';

  return `${toneInstr}

Rewrite the text below in your own voice. ${strengthDesc}

${lengthInstr}

=== KEY PRINCIPLES ===

1. CREATIVE GRAMMAR — never use only standard Subject-Verb-Object order
   - INVERSIONS: "Rarely do we see..." / "Gone are the days when..."
   - FRONTED ADVERBIALS: "Deep in the methodology, a problem lurks."
   - CLEFT SENTENCES: "What surprised me was..." / "It was the third variable that broke everything."
   - PARTICIPIAL PHRASES: "Having spent three months on this, I can say..."
   Alternate between these and normal SVO. Don't use the same trick twice in a row.

2. BREAK FORMULAIC FLOW — NEVER chain clauses with ", and" or ", but"
   - Use semicolons: "The data looked clean; the conclusions were anything but."
   - Use parenthetical asides: "The growth rate (which nobody expected) held steady."
   - Use dashes: "Teachers adopted the tools — reluctantly at first."
   - Split into separate sentences

3. CONFIDENT VOICE — 70% assertive, 30% questioning
   - Make DEFINITIVE claims: "The data is clear" / "This changes everything"
   - Only hedge ONE specific aspect per paragraph
   - Avoid pervasive uncertainty ("might", "could", "perhaps") — GPTZero flags this

4. CONCRETE LANGUAGE
   - Use sensory/experiential language: "spreadsheets glowing at midnight" not "data analysis"
   - Mix abstract claims with tangible examples immediately after

5. PRESERVE ALL FACTS
   Keep every factual claim, number, and argument. Do not invent information.

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": [
    { "original": "phrase from input", "replacement": "rewritten phrase", "reason": "brief reason" }
  ]
}

List every changed phrase in the changes array.`;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/prompts/rewrite.prompt.ts
git commit -m "feat(humanize): add stage 1 Gemini rewrite prompt builder"
```

---

## Task 8: Create the cross-rewrite prompt builder (Stage 2)

**Files:**
- Create: `backend/src/services/humanizer/prompts/cross-rewrite.prompt.ts`

- [ ] **Step 1: Write the prompt builder**

```typescript
// backend/src/services/humanizer/prompts/cross-rewrite.prompt.ts

// Decision: Stage 2 prompt for GPT. Critical instruction: PRESERVE the perturbations
// (contractions, fillers, sentence splits, em dashes, conjunction starters) introduced
// by the perturbation engine — otherwise GPT will "fix" them back into smooth LLM-style
// text and undo the breakthrough piece. Cross-model rewriting is meant to mix GPT's
// distribution over Gemini's perturbed output, not to clean it up.

export function buildCrossRewritePrompt(tone: string): string {
  const toneNote =
    tone === 'academic'
      ? 'Maintain an academic register — but with the personality of someone who actually cares about the topic.'
      : tone === 'casual'
        ? 'Maintain a casual, conversational register.'
        : 'Maintain a persuasive, opinionated register.';

  return `You are rewriting text that has already been humanized once and then deliberately perturbed for stylistic variety. Your job is to rewrite each sentence in your own voice WHILE PRESERVING the human-like irregularities the previous pass introduced.

${toneNote}

=== CRITICAL: PRESERVE THESE PERTURBATIONS ===

The input intentionally contains:
- Contractions ("don't", "it's", "won't") — KEEP them, do not expand to "do not", "it is"
- Sentence-starting fillers ("Honestly,", "Look,", "I mean,", "Actually,") — KEEP them
- Sentences starting with conjunctions ("And", "But", "So") — KEEP them, this is intentional
- Em dashes (—), semicolons, and ellipses (…) — KEEP them, do not replace with periods or commas
- Short fragmented sentences split from longer ones — KEEP them split
- Unusual synonym choices — KEEP them, do not "smooth" them back to common words

If you remove or smooth out these features, the output will fail AI detection. They are FEATURES, not bugs.

=== WHAT YOU SHOULD DO ===

1. Rewrite the underlying sentences in your own phrasing — change verb choices, restructure clauses, vary openings
2. Keep all facts, numbers, claims, and arguments intact
3. The output should READ as if you wrote it from scratch — but retain the perturbation features above
4. Aim for the same length (±15%) as the input

=== ANTI-PATTERNS TO AVOID ===

- Do NOT chain clauses with ", and it..." or ", but it..." (use semicolons or split sentences)
- Do NOT use formulaic transitions ("Furthermore", "Moreover", "Additionally", "In conclusion")
- Do NOT use these AI-flagged words: delve, leverage, utilize, foster, navigate, robust, innovative, seamless, cutting-edge, multifaceted, comprehensive, landscape, realm, tapestry, synergy, testament, myriad, paradigm shift
- Do NOT make the text uniformly hedged — be confident in 70% of statements

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": []
}

The "changes" array can be empty for this stage.`;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/prompts/cross-rewrite.prompt.ts
git commit -m "feat(humanize): add stage 2 GPT cross-rewrite prompt with perturbation preservation"
```

---

## Task 9: Create the polish prompt builder (Stage 3)

**Files:**
- Create: `backend/src/services/humanizer/prompts/polish.prompt.ts`

- [ ] **Step 1: Write the prompt builder**

```typescript
// backend/src/services/humanizer/prompts/polish.prompt.ts

// Decision: Stage 3 polish pass — minimal Gemini rewrite at low temperature (0.3 in the
// pipeline). Only fixes grammatical errors or jarring awkwardness from the perturbation
// passes. Does NOT rewrite content. Same critical instruction as cross-rewrite: preserve
// the perturbation features.

export function buildPolishPrompt(): string {
  return `You are a light-touch editor. The text below has been through multiple rewrites and contains intentional stylistic features that must be preserved. Your job is ONLY to fix obvious grammatical errors or jarring awkwardness — NOT to rewrite or "improve" the style.

=== PRESERVE THESE INTENTIONAL FEATURES (DO NOT TOUCH) ===

- Contractions like "don't", "it's", "won't"
- Sentence-starting fillers like "Honestly,", "Look,", "I mean,", "Actually,"
- Sentences starting with "And", "But", "So" — KEEP these
- Em dashes (—), semicolons (;), ellipses (…)
- Short fragmented sentences
- Unusual synonym choices that read slightly off

These are FEATURES. Do not normalize them.

=== ONLY FIX ===

- Grammatical errors (subject-verb agreement, wrong tense, etc.)
- Sentences where two perturbations made the meaning unclear
- Obvious typos or doubled words ("the the")
- Punctuation that breaks the sentence (e.g., a comma where a sentence should end)

=== DO NOT ===

- Reword sentences that are already understandable
- Replace contractions with their expanded forms
- Combine short sentences into longer ones
- Replace em dashes/semicolons with commas/periods
- Add transition words ("Furthermore", "Moreover", "Additionally")
- Change vocabulary even if it sounds unusual

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the polished text as plain text",
  "changes": []
}

The "changes" array stays empty for this stage.`;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/prompts/polish.prompt.ts
git commit -m "feat(humanize): add stage 3 Gemini polish prompt (preserves perturbations)"
```

---

## Task 10: Refactor humanizer.service.ts to use the new linear pipeline

**Files:**
- Modify: `backend/src/services/humanizer/humanizer.service.ts`

- [ ] **Step 1: Replace the entire file content**

Replace the file with:

```typescript
// backend/src/services/humanizer/humanizer.service.ts

// Decision (v7): Linear cross-model + perturbation pipeline replaces the v6 iterative
// critic loop. The breakthrough is the perturbation layer (non-LLM transformations
// between LLM passes), which raises per-token perplexity in ways no LLM can produce.
// Pipeline: Gemini rewrite → perturb → GPT cross-rewrite → perturb → Gemini polish.
// See docs/superpowers/specs/2026-04-28-humanize-crossmodel-perturbation-design.md

import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { GeminiService } from '@/services/ai/gemini.service';
import { OpenAIService } from '@/services/ai/openai.service';
import { AIDetectorEngine } from '@/services/ai-detector';
import { PerturbationEngine } from './perturbation/perturbation.engine';
import { buildRewritePrompt } from './prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from './prompts/cross-rewrite.prompt';
import { buildPolishPrompt } from './prompts/polish.prompt';

const GEMINI_MODEL = 'gemini-3-flash-preview';
const OPENAI_MODEL = 'gpt-5.5';

// Decision: Strip Unicode invisible characters that some models inject as watermarks.
// Em dash (U+2014) is preserved as a spaced em dash since it's used by perturbation.
function stripBannedCharacters(text: string): string {
  return text
    .replace(/\u200B/g, '')     // Zero-width space → strip
    .replace(/\u202F/g, ' ')    // Narrow no-break space → normal space
    .replace(/\u2003/g, ' ');   // Em space → normal space
}

type TokenStep = {
  step: 'gemini_rewrite' | 'gpt_cross_rewrite' | 'gemini_polish';
  model: string;
  inputTokens: number;
  outputTokens: number;
};

type TokenUsage = {
  steps: TokenStep[];
  totalInputTokens: number;
  totalOutputTokens: number;
};

type PipelineResult = {
  rewrittenText: string;
  changes: Array<{ original: string; replacement: string; reason: string }>;
  aiScoreIn: number;
  aiScoreOut: number;
  tokenUsage: TokenUsage;
  iterations: number; // Always 1 in v7 — kept for backward compat with HumanizeJob model
};

function parseRewriteJson(raw: string): { rewrittenText: string; changes: any[] } {
  try {
    const parsed = JSON.parse(raw);
    return {
      rewrittenText: parsed.rewrittenText || raw,
      changes: parsed.changes || [],
    };
  } catch {
    return { rewrittenText: raw, changes: [] };
  }
}

export class HumanizerService {
  static buildSystemPrompt(tone: string, strength: number, lengthMode: string): string {
    return buildRewritePrompt(tone, strength, lengthMode);
  }

  static async checkAiScore(text: string): Promise<number> {
    const result = await AIDetectorEngine.detect(text);
    return result.score;
  }

  // Legacy single-pass method preserved for backward compatibility with any callers
  // that haven't migrated to humanizePipeline. Uses only Stage 1 (Gemini rewrite).
  static async humanize(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string
  ): Promise<{ rewrittenText: string; changes: Array<{ original: string; replacement: string; reason: string }> }> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildRewritePrompt(tone, strength, lengthMode);

    const { text: result } = await ai.tryWithFallback('humanize', async (service) => {
      return service.chat(systemPrompt, text, {
        temperature: 0.9,
        maxTokens: 4096,
        jsonMode: true,
      });
    });

    return parseRewriteJson(result);
  }

  static async humanizeStream(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onChunk: (chunk: string) => void
  ): Promise<string> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildRewritePrompt(tone, strength, lengthMode);

    return ai.tryWithFallback('humanize-stream', async (service) => {
      return service.chatStream(systemPrompt, text, onChunk, {
        temperature: 0.9,
        maxTokens: 4096,
      });
    });
  }

  static async humanizePipeline(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onStage?: (stage: string, data: any) => void
  ): Promise<PipelineResult> {
    const tokenSteps: TokenStep[] = [];
    const wordCount = text.split(/\s+/).length;
    console.log('[Humanizer v7] Pipeline started | tone=%s strength=%d length=%s words=%d', tone, strength, lengthMode, wordCount);

    // --- Input AI score (informational only) ---
    const aiScoreIn = await this.checkAiScore(text);
    console.log('[Humanizer v7] Input AI score: %d', aiScoreIn);
    onStage?.('ai_score_in', { score: aiScoreIn });

    // --- Stage 1: Gemini Rewrite ---
    onStage?.('stage', { stage: 'rewriting', step: 'gemini_rewrite' });
    const rewritePrompt = buildRewritePrompt(tone, strength, lengthMode);
    const stage1 = await GeminiService.chat(rewritePrompt, text, {
      temperature: 0.9,
      maxTokens: 4096,
      jsonMode: true,
    });
    let { rewrittenText: stage1Text, changes: stage1Changes } = parseRewriteJson(stage1.text);
    stage1Text = stripBannedCharacters(stage1Text);
    console.log('[Humanizer v7] Stage 1 (Gemini rewrite) done | in=%d out=%d tokens', stage1.usage.inputTokens, stage1.usage.outputTokens);
    tokenSteps.push({
      step: 'gemini_rewrite',
      model: GEMINI_MODEL,
      inputTokens: stage1.usage.inputTokens,
      outputTokens: stage1.usage.outputTokens,
    });

    // --- Perturbation Layer 1 ---
    onStage?.('stage', { stage: 'perturbing', step: 'perturbation_1' });
    const perturbed1 = PerturbationEngine.perturb(stage1Text, strength);
    console.log('[Humanizer v7] Perturbation 1 done | in_chars=%d out_chars=%d', stage1Text.length, perturbed1.length);

    // --- Stage 2: GPT Cross-Rewrite ---
    onStage?.('stage', { stage: 'rewriting', step: 'gpt_cross_rewrite' });
    const crossRewritePrompt = buildCrossRewritePrompt(tone);
    const stage2 = await OpenAIService.chat(crossRewritePrompt, perturbed1, {
      maxTokens: 4096,
      jsonMode: true,
    });
    let { rewrittenText: stage2Text } = parseRewriteJson(stage2.text);
    stage2Text = stripBannedCharacters(stage2Text);
    console.log('[Humanizer v7] Stage 2 (GPT cross-rewrite) done | in=%d out=%d tokens', stage2.usage.inputTokens, stage2.usage.outputTokens);
    tokenSteps.push({
      step: 'gpt_cross_rewrite',
      model: OPENAI_MODEL,
      inputTokens: stage2.usage.inputTokens,
      outputTokens: stage2.usage.outputTokens,
    });

    // --- Perturbation Layer 2 ---
    onStage?.('stage', { stage: 'perturbing', step: 'perturbation_2' });
    const perturbed2 = PerturbationEngine.perturb(stage2Text, strength);
    console.log('[Humanizer v7] Perturbation 2 done | in_chars=%d out_chars=%d', stage2Text.length, perturbed2.length);

    // --- Stage 3: Gemini Polish ---
    onStage?.('stage', { stage: 'polishing', step: 'gemini_polish' });
    const polishPrompt = buildPolishPrompt();
    const stage3 = await GeminiService.chat(polishPrompt, perturbed2, {
      temperature: 0.3,
      maxTokens: 4096,
      jsonMode: true,
    });
    let { rewrittenText: finalText } = parseRewriteJson(stage3.text);
    finalText = stripBannedCharacters(finalText);
    console.log('[Humanizer v7] Stage 3 (Gemini polish) done | in=%d out=%d tokens', stage3.usage.inputTokens, stage3.usage.outputTokens);
    tokenSteps.push({
      step: 'gemini_polish',
      model: GEMINI_MODEL,
      inputTokens: stage3.usage.inputTokens,
      outputTokens: stage3.usage.outputTokens,
    });

    // --- Final score (informational only — no iteration) ---
    const aiScoreOut = await this.checkAiScore(finalText);
    onStage?.('score', { score: aiScoreOut });

    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);
    console.log('[Humanizer v7] Pipeline complete | score: %d → %d | tokens: in=%d out=%d', aiScoreIn, aiScoreOut, totalInputTokens, totalOutputTokens);

    return {
      rewrittenText: finalText,
      changes: stage1Changes,
      aiScoreIn,
      aiScoreOut,
      tokenUsage: { steps: tokenSteps, totalInputTokens, totalOutputTokens },
      iterations: 1,
    };
  }

  // Credit cost formula. 1 credit per 50 words with a minimum of 2 per run.
  // Frontend mirrors this exact formula in HumBoard.tsx — keep them in lockstep.
  static calculateCredits(wordCount: number): number {
    return Math.max(2, Math.ceil(wordCount / 50));
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/humanizer/humanizer.service.ts
git commit -m "feat(humanize): refactor pipeline to v7 cross-model + perturbation

Linear pipeline: Gemini rewrite → perturb → GPT cross-rewrite → perturb → Gemini polish.
Removes iterative critic loop. Score is informational only (does not gate iteration)."
```

---

## Task 11: Verify the HumanizeJob model still accepts the new tokenUsage shape

**Files:**
- Read: `backend/src/models/HumanizeJob.ts`

- [ ] **Step 1: Read the model**

Read `backend/src/models/HumanizeJob.ts` and check the `tokenUsage` and `iterations` field definitions.

- [ ] **Step 2: Verify shape compatibility**

Confirm:
- `tokenUsage.steps` accepts strings for `step` field (not constrained to old enum like `'preprocess' | 'critic' | 'humanizer'`)
- `iterations` field accepts a number (we always pass 1 in v7)

If `step` is constrained to old enum values, update the schema to also accept the new values: `'gemini_rewrite' | 'gpt_cross_rewrite' | 'gemini_polish'` (or relax to a generic string).

- [ ] **Step 3: If schema changes were needed, verify TypeScript**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 4: Commit (only if schema was modified)**

```bash
git add backend/src/models/HumanizeJob.ts
git commit -m "chore(humanize): allow new v7 stage names in HumanizeJob.tokenUsage.steps"
```

---

## Task 12: Create end-to-end manual pipeline test script

**Files:**
- Create: `backend/src/scripts/test-humanize-pipeline.ts`

- [ ] **Step 1: Write the script**

```typescript
// backend/src/scripts/test-humanize-pipeline.ts

// Decision: Manual end-to-end pipeline test. Runs the full v7 pipeline against the
// existing humanizer test fixtures and prints input/output for visual inspection plus
// a manual GPTZero check. Following the pattern of score-samples.ts.
//
// Usage:
//   cd backend
//   npx ts-node -r tsconfig-paths/register src/scripts/test-humanize-pipeline.ts

import 'dotenv/config';
import { HumanizerService } from '@/services/humanizer/humanizer.service';
import * as fs from 'fs';
import * as path from 'path';

const SAMPLES = [
  {
    name: 'AI English',
    text: fs.readFileSync(path.resolve(__dirname, '../../../tests/humanizer/en.txt'), 'utf-8').trim(),
  },
  {
    name: 'AI Vietnamese',
    text: fs.readFileSync(path.resolve(__dirname, '../../../tests/humanizer/vi.txt'), 'utf-8').trim(),
  },
];

async function main() {
  for (const sample of SAMPLES) {
    console.log(`\n${'='.repeat(80)}`);
    console.log(`SAMPLE: ${sample.name}`);
    console.log('='.repeat(80));
    console.log('\n--- INPUT ---\n');
    console.log(sample.text);

    const result = await HumanizerService.humanizePipeline(
      sample.text,
      'academic',
      50,
      'match',
      (stage, data) => console.log(`  [stage] ${stage}:`, data),
    );

    console.log('\n--- OUTPUT ---\n');
    console.log(result.rewrittenText);
    console.log('\n--- METRICS ---');
    console.log(`  Score: ${result.aiScoreIn} → ${result.aiScoreOut}`);
    console.log(`  Tokens: in=${result.tokenUsage.totalInputTokens} out=${result.tokenUsage.totalOutputTokens}`);
    console.log('\n  Manual check: paste OUTPUT into https://gptzero.me and verify score drops.');
  }
}

main().catch((err) => {
  console.error('Pipeline test failed:', err);
  process.exit(1);
});
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd backend && npx tsc --noEmit; echo "EXIT: $?"`
Expected: `EXIT: 0`

- [ ] **Step 3: Run the script**

Run: `cd backend && npx ts-node -r tsconfig-paths/register src/scripts/test-humanize-pipeline.ts`
Expected: Both samples run end-to-end without error. Each prints input, output, and metrics.

If errors occur:
- API key missing → check `.env` for `GEMINI_API_KEY` and `OPENAI_API_KEY`
- JSON parse error → check that the polish prompt is producing valid JSON; may need to tighten the JSON-only instruction
- Empty output → check that perturbation isn't destroying the text (look at `out_chars` in logs)

- [ ] **Step 4: Manual GPTZero verification**

Copy each `--- OUTPUT ---` section into https://gptzero.me. Record results:
- English sample: Was AI 100% in v6 — record new v7 score
- Vietnamese sample: Record new v7 score
- Acceptance criterion: Both should show meaningful confidence drop. If GPTZero still says 100% for both, see Task 14 troubleshooting.

- [ ] **Step 5: Commit the test script**

```bash
git add backend/src/scripts/test-humanize-pipeline.ts
git commit -m "test(humanize): add end-to-end pipeline test script for manual GPTZero check"
```

---

## Task 13: Run the full app and test via the UI

**Files:** None modified

- [ ] **Step 1: Start the backend dev server**

Run in a separate terminal: `cd /Users/caonguyenvan/project/dothesis/backend && npm run dev`
Expected: Server starts on its configured port without errors. Watch for any import errors related to the moved file.

- [ ] **Step 2: Start the frontend**

Run in another terminal: `cd /Users/caonguyenvan/project/dothesis/frontend && npm run dev`

- [ ] **Step 3: Open the humanizer page in a browser**

Navigate to the humanizer page. Paste an AI-generated sample text. Run humanization with default settings (academic, strength 50).

- [ ] **Step 4: Verify the SSE events flow correctly**

Open the browser DevTools network tab. Find the `/humanize/run` request. Check the EventStream tab. Expected events in order:
- `ai_score_in`
- `stage` (rewriting, gemini_rewrite)
- `stage` (perturbing, perturbation_1)
- `stage` (rewriting, gpt_cross_rewrite)
- `stage` (perturbing, perturbation_2)
- `stage` (polishing, gemini_polish)
- `score`
- `done`

If the frontend visibly breaks (e.g., progress indicator stalls), check what stage names the frontend listens for in `frontend/components/humanizer/` and adjust the backend event names to match, or update the frontend to handle the new names.

- [ ] **Step 5: Copy the output, paste into GPTZero, record result**

Compare against the v6 baseline (100% AI). Record the v7 score.

- [ ] **Step 6: If frontend changes were needed, commit them**

```bash
git add frontend/...
git commit -m "fix(humanize): update frontend to handle v7 pipeline stage names"
```

---

## Task 14: Tuning loop (only if GPTZero still flags ≥80% AI)

**Goal:** If the v7 pipeline doesn't meaningfully reduce GPTZero confidence, diagnose and tune.

- [ ] **Step 1: Identify which stage is leaving the AI fingerprint**

Run the test script and save outputs at each stage. Modify `test-humanize-pipeline.ts` to log all 5 intermediate texts:
- After Stage 1 (Gemini rewrite)
- After Perturbation 1
- After Stage 2 (GPT cross-rewrite)
- After Perturbation 2
- After Stage 3 (Gemini polish)

Paste each into GPTZero. The first stage where score jumps back to AI is the problem.

- [ ] **Step 2: Apply the targeted fix based on which stage failed**

- **Polish stage broke it (perturbations got smoothed away):** Tighten the polish prompt's "PRESERVE THESE FEATURES" section. Possibly skip polish entirely for an A/B test.
- **Cross-rewrite stage broke it (GPT smoothed perturbations):** Tighten the cross-rewrite prompt's preservation rules with stronger language ("If you remove these features, you have failed the task.")
- **Perturbation rate too low:** Bump rates in `PerturbationEngine.getRate()` from `0.20/0.35/0.50` to `0.30/0.50/0.70`.
- **Synonym dictionary too small:** Add ~50 more entries focused on words showing in the output that GPTZero highlights.
- **All three:** Consider re-adding a perturbation pass after polish (Stage 3 → Perturbation 3).

- [ ] **Step 3: Re-run end-to-end test, verify improvement**

Re-run `test-humanize-pipeline.ts` and re-check GPTZero.

- [ ] **Step 4: Commit the tuning changes**

```bash
git add backend/src/services/humanizer/
git commit -m "tune(humanize): tighten v7 perturbation preservation in <stage> prompt"
```

---

## Task 15: Final verification and PR

- [ ] **Step 1: Run all tests**

```bash
cd backend && npx tsc --noEmit && npx ts-node -r tsconfig-paths/register src/scripts/test-perturbation.ts
```
Expected: No TypeScript errors, all 16 perturbation tests pass.

- [ ] **Step 2: Verify git log shows clean commit history**

Run: `git log master..HEAD --oneline`
Expected: ~12-15 commits in logical order (setup, dictionary, markers, ops, engine, tests, prompts, refactor, end-to-end test, manual verification).

- [ ] **Step 3: Push the branch and open a PR**

```bash
git push -u origin feat/humanize-crossmodel-perturbation
```

Then open a PR with a summary describing:
- The v6 → v7 architecture change
- Manual GPTZero verification results (before/after percentages)
- The 3 LLM stages + 2 perturbation layers
- Test script locations

---

## Self-Review Checklist (completed during plan writing)

- ✅ Spec coverage: Each spec section maps to at least one task
  - Pipeline architecture → Task 10
  - Perturbation Engine + 6 ops → Tasks 4, 5
  - Synonym dictionary → Task 2
  - Human markers → Task 3
  - Language awareness → Operations + engine handle EN/VI
  - Prompt builders (3) → Tasks 7, 8, 9
  - File structure → Task 1
  - Module boundaries → Task 5 (engine), Tasks 7-9 (prompts)
  - API contract preservation → Verified in Tasks 11, 13
  - Error handling → Pipeline aborts on stage failure (existing pattern preserved)
  - Testing strategy → Task 6 (unit), Task 12 (e2e), Task 13 (UI)
  - Rollout/manual GPTZero check → Tasks 12-13, tuning loop in Task 14
- ✅ No placeholders — every code step shows the actual code
- ✅ Type consistency — `PerturbationOp` signature, `RNG` type, `Lang` type all used consistently across operations.ts, engine, and tests
- ✅ Stage step names match across the service, prompt builders, and test script (`gemini_rewrite`, `gpt_cross_rewrite`, `gemini_polish`)
