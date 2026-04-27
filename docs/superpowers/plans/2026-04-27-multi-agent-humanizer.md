# Multi-Agent Humanizer Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-pass humanization with a multi-agent pipeline (Gemini preprocess -> GPT critic -> GPT humanizer loop) that targets AI detection scores below 30.

**Architecture:** Pipeline lives in `humanizer.service.ts`. AI service `chat()` methods return `{ text, usage }` for token tracking. The pipeline is transport-agnostic via an `onStage` callback — works for SSE routes, sync routes, and future queue workers.

**Tech Stack:** TypeScript, OpenAI SDK (`gpt-5.5`), Google GenAI SDK (`gemini-3-flash-preview`), Anthropic SDK, Express SSE, Typegoose/MongoDB, React/Redux (frontend).

---

### Task 1: Update AI Service Return Types

**Files:**
- Modify: `backend/src/services/ai/openai.service.ts`
- Modify: `backend/src/services/ai/gemini.service.ts`
- Modify: `backend/src/services/ai/claude.service.ts`
- Modify: `backend/src/services/ai/ai.service.manager.ts`

- [ ] **Step 1: Add AIChatResult type to ai.service.manager.ts**

Add the shared type at the top of the file, before the `AIProvider` type:

```typescript
export type AIChatResult = {
  text: string;
  usage: { inputTokens: number; outputTokens: number };
};
```

- [ ] **Step 2: Update OpenAIService.chat() to return AIChatResult**

In `backend/src/services/ai/openai.service.ts`, change the `chat` method return type from `Promise<string>` to `Promise<AIChatResult>`. Add `presence_penalty` and `frequency_penalty` to the options type. Extract token usage from `response.usage`:

```typescript
import { AIChatResult } from './ai.service.manager';

export class OpenAIService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: {
      temperature?: number;
      maxTokens?: number;
      jsonMode?: boolean;
      presencePenalty?: number;
      frequencyPenalty?: number;
    } = {}
  ): Promise<AIChatResult> {
    const response = await openai.chat.completions.create({
      // Decision: Upgraded from gpt-4o to gpt-5.5 (released April 2026).
      // gpt-4o humanization output was too robotic — GPTZero flagged it for
      // "Mechanical Precision" and "Lacks Creative Grammar". gpt-5.5 follows
      // complex creative instructions much better.
      model: 'gpt-5.5',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: options.temperature ?? 0.7,
      // Decision: GPT-5.5 requires max_completion_tokens instead of max_tokens.
      max_completion_tokens: options.maxTokens ?? 4096,
      response_format: options.jsonMode ? { type: 'json_object' } : undefined,
      // Decision: Added presence/frequency penalties for multi-agent humanizer pipeline.
      // presence_penalty encourages branching into new concepts.
      // frequency_penalty discourages word repetition, making text more dynamic.
      presence_penalty: options.presencePenalty ?? 0,
      frequency_penalty: options.frequencyPenalty ?? 0,
    });

    const text = response.choices[0]?.message?.content || '';
    return {
      text,
      usage: {
        inputTokens: response.usage?.prompt_tokens ?? 0,
        outputTokens: response.usage?.completion_tokens ?? 0,
      },
    };
  }

  // chatStream stays unchanged — returns string
```

- [ ] **Step 3: Update GeminiService.chat() to return AIChatResult**

In `backend/src/services/ai/gemini.service.ts`, change return type and extract usage metadata:

```typescript
import { AIChatResult } from './ai.service.manager';

export class GeminiService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number; jsonMode?: boolean } = {}
  ): Promise<AIChatResult> {
    const response = await genai.models.generateContent({
      // Decision: Upgraded from gemini-2.5-pro to gemini-3-flash-preview (Gemini 3 series).
      // Pro-level intelligence at Flash speed/pricing. Model ID requires "-preview" suffix.
      model: 'gemini-3-flash-preview',
      contents: userPrompt,
      config: {
        systemInstruction: systemPrompt,
        temperature: options.temperature ?? 0.7,
        maxOutputTokens: options.maxTokens ?? 4096,
        responseMimeType: options.jsonMode ? 'application/json' : undefined,
      },
    });

    const text = response.text || '';
    return {
      text,
      usage: {
        inputTokens: (response as any).usageMetadata?.promptTokenCount ?? 0,
        outputTokens: (response as any).usageMetadata?.candidatesTokenCount ?? 0,
      },
    };
  }

  // chatStream stays unchanged — returns string
```

- [ ] **Step 4: Update ClaudeService.chat() to return AIChatResult**

In `backend/src/services/ai/claude.service.ts`, change return type and extract usage:

```typescript
import { AIChatResult } from './ai.service.manager';

export class ClaudeService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<AIChatResult> {
    const response = await anthropic.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: options.maxTokens ?? 4096,
      system: systemPrompt,
      messages: [{ role: 'user', content: userPrompt }],
      temperature: options.temperature ?? 0.7,
    });

    const textBlock = response.content.find((b: any) => b.type === 'text');
    const text = textBlock ? (textBlock as any).text : '';
    return {
      text,
      usage: {
        inputTokens: response.usage?.input_tokens ?? 0,
        outputTokens: response.usage?.output_tokens ?? 0,
      },
    };
  }

  // chatStream stays unchanged — returns string
```

- [ ] **Step 5: Update callers in citation.service.ts**

In `backend/src/services/citation.service.ts`, the 3 callers of `.chat()` currently expect a `string`. Update each to destructure `{ text }`:

At line ~132-134, change:
```typescript
// Old:
const result = await ai.tryWithFallback('extract-claims', async (service) => {
  return service.chat(systemPrompt, text, { temperature: 0.3, jsonMode: true });
});
// New:
const { text: result } = await ai.tryWithFallback('extract-claims', async (service) => {
  return service.chat(systemPrompt, text, { temperature: 0.3, jsonMode: true });
});
```

At line ~165-167, change:
```typescript
// Old:
const result = await ai.tryWithFallback('rank-candidates', async (service) => {
  return service.chat(systemPrompt, userPrompt, { temperature: 0.3, jsonMode: true });
});
// New:
const { text: result } = await ai.tryWithFallback('rank-candidates', async (service) => {
  return service.chat(systemPrompt, userPrompt, { temperature: 0.3, jsonMode: true });
});
```

At line ~191-193, change:
```typescript
// Old:
return ai.tryWithFallback('format-citation', async (service) => {
  return service.chat(systemPrompt, userPrompt, { temperature: 0.1 });
});
// New:
const { text } = await ai.tryWithFallback('format-citation', async (service) => {
  return service.chat(systemPrompt, userPrompt, { temperature: 0.1 });
});
return text;
```

- [ ] **Step 6: Verify the backend compiles**

Run: `cd backend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 7: Commit**

```bash
git add backend/src/services/ai/openai.service.ts backend/src/services/ai/gemini.service.ts backend/src/services/ai/claude.service.ts backend/src/services/ai/ai.service.manager.ts backend/src/services/citation.service.ts
git commit -m "refactor: AI service chat() returns AIChatResult with token usage

Breaking change: chat() now returns { text, usage } instead of string.
Added presencePenalty/frequencyPenalty options to OpenAI service.
Updated all callers in citation.service.ts."
```

---

### Task 2: Update HumanizeJob Model

**Files:**
- Modify: `backend/src/models/HumanizeJob.ts`

- [ ] **Step 1: Add tokenUsage and iterations fields**

In `backend/src/models/HumanizeJob.ts`, add the new fields after the existing `status` field:

```typescript
@prop({ default: 0 })
public iterations!: number;

@prop({
  type: () => Object,
  default: () => ({ steps: [], totalInputTokens: 0, totalOutputTokens: 0 }),
})
public tokenUsage!: {
  steps: Array<{
    step: string;
    model: string;
    iteration: number;
    inputTokens: number;
    outputTokens: number;
  }>;
  totalInputTokens: number;
  totalOutputTokens: number;
};
```

- [ ] **Step 2: Verify the backend compiles**

Run: `cd backend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add backend/src/models/HumanizeJob.ts
git commit -m "feat: add tokenUsage and iterations fields to HumanizeJob model"
```

---

### Task 3: Build Multi-Agent Pipeline in humanizer.service.ts

**Files:**
- Modify: `backend/src/services/humanizer.service.ts`

- [ ] **Step 1: Add ban lists and type definitions**

Add at the top of the file, after imports:

```typescript
import { GeminiService } from '@/services/ai/gemini.service';
import { OpenAIService } from '@/services/ai/openai.service';

// Decision: Multi-agent pipeline — each model is called directly by name
// instead of going through AIServiceManager fallback. The pipeline needs
// specific models for specific roles (Gemini for speed, GPT for quality).

const GEMINI_MODEL = 'gemini-3-flash-preview';
const OPENAI_MODEL = 'gpt-5.5';

// Decision: Ban list of words/phrases that AI detectors flag instantly.
// Sources: GPTZero docs, walterwrites.ai, thehumanizeai.pro (April 2026).
// These words have statistically elevated frequency in LLM output vs human writing.
const BANNED_WORDS: string[] = [
  // Overused AI verbs
  'delve', 'leverage', 'utilize', 'harness', 'streamline', 'underscore',
  'foster', 'spearhead', 'navigate', 'capitalize', 'embark', 'unlock',
  'empower', 'facilitate', 'optimize', 'pave the way',
  // Inflated AI adjectives/adverbs
  'pivotal', 'robust', 'innovative', 'seamless', 'cutting-edge',
  'multifaceted', 'comprehensive', 'crucially', 'notably', 'importantly',
  'significantly', 'groundbreaking',
  // AI filler nouns/phrases
  'landscape', 'realm', 'tapestry', 'synergy', 'testament', 'underpinnings',
  'beacon', 'treasure trove', 'myriad', 'game changer', 'paradigm shift',
  // AI transition/filler phrases
  'furthermore', 'moreover', 'in conclusion', "it's worth noting",
  'it should be mentioned', "in today's world", "in today's fast-paced world",
  'at the forefront of', 'bridging the gap', 'push the boundaries',
  'lay the groundwork', 'in terms of', 'subsequently', 'accordingly',
  'in essence',
];

// Decision: AI models inject hidden Unicode characters that detectors flag.
// Em dash (U+2014) is the most common — ChatGPT overuses it heavily.
// Zero-width spaces and special spaces are used as invisible watermarks.
function stripBannedCharacters(text: string): string {
  return text
    .replace(/\u2014/g, ', ')   // Em dash → comma
    .replace(/\u200B/g, '')     // Zero-width space → strip
    .replace(/\u202F/g, ' ')    // Narrow no-break space → normal space
    .replace(/\u2003/g, ' ');   // Em space → normal space
}

type TokenStep = {
  step: 'preprocess' | 'critic' | 'humanizer';
  model: string;
  iteration: number;
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
  iterations: number;
};
```

- [ ] **Step 2: Add Gemini preprocessor prompt builder**

Add after the existing `buildHumanizePrompt` function:

```typescript
function buildPreprocessPrompt(): string {
  return `You are a text structure editor. Your job is to restructure text for natural sentence variety — NOT to rewrite content.

=== RULES ===

1. VARY SENTENCE LENGTHS DRASTICALLY
   - Mix very short sentences (under 10 words) with long ones (25+ words)
   - Never have 3 consecutive sentences of similar length
   - Split overly long sentences. Merge overly short ones where natural.

2. BREAK PARALLEL CONSTRUCTIONS
   - If multiple sentences follow the same pattern (Subject-Verb-Object, Subject-Verb-Object), restructure some
   - Change sentence openings — don't start 3+ sentences the same way
   - Mix declarative, interrogative, and conditional structures

3. REORDER WITHIN PARAGRAPHS
   - Where logical, change the order of sentences within a paragraph
   - Lead with a different point than the original when it still makes sense

4. PRESERVE EVERYTHING ELSE
   - Keep all facts, numbers, arguments, and meaning exactly as-is
   - Keep the same language (if Vietnamese, output Vietnamese; if English, output English)
   - Do NOT rewrite vocabulary or tone — only restructure

Output the restructured text as plain text. No JSON, no markdown.`;
}
```

- [ ] **Step 3: Add GPT critic prompt builder**

Add after the preprocessor prompt:

```typescript
function buildCriticPrompt(): string {
  const bannedList = BANNED_WORDS.join(', ');
  return `You are an expert AI text detector. Analyze the provided text and identify specific patterns that AI detection tools (GPTZero, Turnitin, Originality.ai) would flag.

Scan for these issues:
- **uniform_length**: Sentences of similar length creating a predictable rhythm
- **predictable_transition**: Smooth logical connectors used systematically (e.g., "Furthermore", "Additionally")
- **repetitive_opening**: Multiple sentences starting with the same pattern
- **consistent_register**: Uniform formality level throughout — no natural register mixing
- **vocabulary_uniformity**: Same level of vocabulary sophistication throughout, no colloquialisms
- **lack_personality**: No personal opinion, humor, rhetorical questions, or tangential observations
- **banned_word**: Any occurrence of these known AI-flagged words/phrases: ${bannedList}

For each issue found, provide the exact location (quote the text), describe the problem, and suggest a specific fix.

Respond with valid JSON only:
{
  "issues": [
    {
      "type": "uniform_length | predictable_transition | repetitive_opening | consistent_register | vocabulary_uniformity | lack_personality | banned_word",
      "location": "exact quote from text",
      "description": "what makes this detectable",
      "suggestion": "specific fix"
    }
  ],
  "overallAssessment": "1-2 sentence summary of how AI-detectable this text is"
}`;
}
```

- [ ] **Step 4: Add GPT humanizer prompt builder (critique-aware)**

Add after the critic prompt. This builds on the existing `buildHumanizePrompt` but adds critique context and ban list enforcement:

```typescript
function buildHumanizerWithCritiquePrompt(
  tone: string,
  strength: number,
  lengthMode: string,
  critique: string
): string {
  const basePrompt = buildHumanizePrompt(tone, strength, lengthMode);
  const bannedList = BANNED_WORDS.join(', ');

  return `${basePrompt}

=== CRITIC FEEDBACK (fix ALL of these issues) ===

${critique}

=== BANNED WORDS (NEVER use any of these) ===

${bannedList}

If any of these words appear in the input, replace them with natural alternatives. Never introduce any of these words in your rewrite.`;
}
```

- [ ] **Step 5: Add the humanizePipeline method**

Add to the `HumanizerService` class, after the existing `humanizeStream` method:

```typescript
  static async humanizePipeline(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onStage?: (stage: string, data: any) => void
  ): Promise<PipelineResult> {
    const tokenSteps: TokenStep[] = [];

    const addTokenStep = (step: TokenStep) => {
      tokenSteps.push(step);
    };

    // --- Input AI score ---
    const aiScoreIn = await this.checkAiScore(text);
    onStage?.('ai_score_in', { score: aiScoreIn });

    // --- Stage 1: Gemini Preprocess ---
    onStage?.('stage', { stage: 'preprocessing' });

    const preprocessPrompt = buildPreprocessPrompt();
    const preprocessResult = await GeminiService.chat(preprocessPrompt, text, {
      temperature: 0.7,
      maxTokens: 4096,
    });

    // Decision: Strip banned Unicode characters after Gemini output.
    // Gemini may introduce em dashes and special spaces in its restructuring.
    let currentText = stripBannedCharacters(preprocessResult.text);
    addTokenStep({
      step: 'preprocess',
      model: GEMINI_MODEL,
      iteration: 0,
      inputTokens: preprocessResult.usage.inputTokens,
      outputTokens: preprocessResult.usage.outputTokens,
    });

    // --- Iterative Loop: Critic -> Humanizer -> Score ---
    const MAX_ITERATIONS = 3;
    const TARGET_SCORE = 30;
    let bestResult = { text: currentText, score: 100, changes: [] as any[] };
    let iterations = 0;

    for (let i = 1; i <= MAX_ITERATIONS; i++) {
      iterations = i;

      // Stage 2: GPT Critic
      onStage?.('stage', { stage: 'critiquing', iteration: i });

      const criticPrompt = buildCriticPrompt();
      const criticResult = await OpenAIService.chat(criticPrompt, currentText, {
        temperature: 0.3,
        maxTokens: 2048,
        jsonMode: true,
      });
      addTokenStep({
        step: 'critic',
        model: OPENAI_MODEL,
        iteration: i,
        inputTokens: criticResult.usage.inputTokens,
        outputTokens: criticResult.usage.outputTokens,
      });

      // Stage 3: GPT Humanizer
      onStage?.('stage', { stage: 'rewriting', iteration: i });

      const humanizerPrompt = buildHumanizerWithCritiquePrompt(
        tone,
        strength,
        lengthMode,
        criticResult.text
      );
      const humanizerResult = await OpenAIService.chat(humanizerPrompt, currentText, {
        temperature: 0.9,
        maxTokens: 4096,
        jsonMode: true,
        // Decision: Penalties force GPT to use varied vocabulary and explore new concepts.
        // presence_penalty=0.3 encourages novel topics; frequency_penalty=0.4 penalizes
        // repeated words. These values were chosen based on OpenAI docs recommendations
        // for creative writing tasks.
        presencePenalty: 0.3,
        frequencyPenalty: 0.4,
      });
      addTokenStep({
        step: 'humanizer',
        model: OPENAI_MODEL,
        iteration: i,
        inputTokens: humanizerResult.usage.inputTokens,
        outputTokens: humanizerResult.usage.outputTokens,
      });

      // Parse humanizer output
      let rewrittenText = humanizerResult.text;
      let changes: any[] = [];
      try {
        const parsed = JSON.parse(humanizerResult.text);
        rewrittenText = parsed.rewrittenText || humanizerResult.text;
        changes = parsed.changes || [];
      } catch {
        // If not valid JSON, use raw text
      }

      // Strip banned characters from output
      rewrittenText = stripBannedCharacters(rewrittenText);
      currentText = rewrittenText;

      // Score check
      const score = await this.checkAiScore(currentText);
      onStage?.('score', { score, iteration: i });

      // Track best result
      if (score < bestResult.score) {
        bestResult = { text: currentText, score, changes };
      }

      // Exit if target reached
      if (score < TARGET_SCORE) {
        break;
      }
    }

    // Build final token usage summary
    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);

    return {
      rewrittenText: bestResult.text,
      changes: bestResult.changes,
      aiScoreIn,
      aiScoreOut: bestResult.score,
      tokenUsage: {
        steps: tokenSteps,
        totalInputTokens,
        totalOutputTokens,
      },
      iterations,
    };
  }
```

- [ ] **Step 6: Update the existing humanize() method to use the new return type**

The existing `humanize()` method still uses `tryWithFallback` which now returns `AIChatResult`. Update it:

```typescript
  static async humanize(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string
  ): Promise<{ rewrittenText: string; changes: Array<{ original: string; replacement: string; reason: string }> }> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    const { text: result } = await ai.tryWithFallback('humanize', async (service) => {
      return service.chat(systemPrompt, text, {
        // Decision: Temperature raised from 0.7 → 0.9 to increase output creativity.
        temperature: 0.9,
        maxTokens: 4096,
        jsonMode: true,
      });
    });

    try {
      return JSON.parse(result);
    } catch {
      return { rewrittenText: result, changes: [] };
    }
  }
```

- [ ] **Step 7: Verify the backend compiles**

Run: `cd backend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 8: Commit**

```bash
git add backend/src/services/humanizer.service.ts
git commit -m "feat: add multi-agent humanizePipeline with ban lists and token tracking

Gemini preprocesses for structural burstiness, GPT critiques AI patterns,
GPT rewrites with critique feedback. Loops up to 3 times targeting score < 30.
Tracks token usage per step with actual model names."
```

---

### Task 4: Update Humanize Route (SSE + Sync + Samples)

**Files:**
- Modify: `backend/src/api/routes/humanize.ts`

- [ ] **Step 1: Update the SSE `/humanize/run` route to use the pipeline**

Replace the existing SSE handler body (the `try` block inside the route, after SSE headers are set) with the pipeline call:

```typescript
    try {
      // Run multi-agent pipeline with SSE stage callbacks
      const result = await HumanizerService.humanizePipeline(
        text,
        tone,
        strength,
        lengthMode,
        (stage, data) => {
          res.write(`data: ${JSON.stringify({ type: stage, ...data })}\n\n`);
        }
      );

      // Deduct credits
      await CreditService.deduct(
        user._id.toString(),
        creditCost,
        'humanize',
        job._id.toString(),
        `Humanize ${wordCount} words`
      );

      // Update job
      job.outputText = result.rewrittenText;
      job.outputHtml = result.rewrittenText;
      job.aiScoreIn = result.aiScoreIn;
      job.aiScoreOut = result.aiScoreOut;
      job.changesCount = result.changes.length;
      job.creditsUsed = creditCost;
      job.iterations = result.iterations;
      job.tokenUsage = result.tokenUsage;
      job.status = 'completed';
      await job.save();

      // Send final result
      res.write(
        `data: ${JSON.stringify({
          type: 'done',
          jobId: job._id,
          rewrittenText: result.rewrittenText,
          changes: result.changes,
          aiScoreIn: result.aiScoreIn,
          aiScoreOut: result.aiScoreOut,
          tokenUsage: result.tokenUsage,
          iterations: result.iterations,
          changesCount: result.changes.length,
          creditsUsed: creditCost,
        })}\n\n`
      );
    } catch (err: any) {
      // Refund on failure
      job.status = 'failed';
      await job.save();
      res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    }
```

- [ ] **Step 2: Add the sync `/humanize/run-sync` route**

Add after the SSE route (before the `/humanize/check-score` route):

```typescript
  // Sync humanize — designed for queue workers, no SSE
  router.post(
    '/humanize/run-sync',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text, tone = 'academic', strength = 50, lengthMode = 'match' } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      const wordCount = DocumentService.countWords(text);
      const creditCost = HumanizerService.calculateCredits(wordCount);

      if (!(await CreditService.hasEnough(user._id.toString(), creditCost))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const job = await HumanizeJobModel.create({
        owner: user._id.toString(),
        inputText: text,
        tone,
        strength,
        lengthMode,
        status: 'processing',
      });

      try {
        const result = await HumanizerService.humanizePipeline(text, tone, strength, lengthMode);

        await CreditService.deduct(
          user._id.toString(),
          creditCost,
          'humanize',
          job._id.toString(),
          `Humanize ${wordCount} words`
        );

        job.outputText = result.rewrittenText;
        job.outputHtml = result.rewrittenText;
        job.aiScoreIn = result.aiScoreIn;
        job.aiScoreOut = result.aiScoreOut;
        job.changesCount = result.changes.length;
        job.creditsUsed = creditCost;
        job.iterations = result.iterations;
        job.tokenUsage = result.tokenUsage;
        job.status = 'completed';
        await job.save();

        return res.json({
          code: Code.Success,
          data: {
            jobId: job._id,
            rewrittenText: result.rewrittenText,
            changes: result.changes,
            aiScoreIn: result.aiScoreIn,
            aiScoreOut: result.aiScoreOut,
            tokenUsage: result.tokenUsage,
            iterations: result.iterations,
            creditsUsed: creditCost,
          },
        });
      } catch (err: any) {
        job.status = 'failed';
        await job.save();
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );
```

- [ ] **Step 3: Add the `/humanize/samples` endpoint**

Add at the end of the route file (before the closing `};`):

```typescript
  // Sample texts for testing — no auth required
  router.get('/humanize/samples', (_req, res) => {
    // Decision: Static AI-generated sample texts for users to test the humanizer.
    // Intentionally written in a robotic AI style so the before/after effect is clear.
    const SAMPLE_TEXTS = [
      {
        id: 'academic',
        label: 'Academic Essay',
        text: `The rapid advancement of artificial intelligence has fundamentally transformed the landscape of modern education. Furthermore, the integration of machine learning algorithms into pedagogical frameworks has demonstrated significant potential for personalized learning experiences. Research indicates that AI-driven adaptive learning platforms can improve student outcomes by approximately 30%, underscoring the pivotal role of technology in contemporary educational paradigms. Moreover, the implementation of natural language processing tools has facilitated more efficient assessment methodologies, enabling educators to provide timely and comprehensive feedback. It is worth noting that these technological innovations have also raised important ethical considerations regarding data privacy and algorithmic bias in educational settings.`,
      },
      {
        id: 'blog',
        label: 'Blog Post',
        text: `In today's fast-paced world, remote work has emerged as a game changer for businesses worldwide. Companies are increasingly leveraging digital collaboration tools to streamline their operations and foster a more inclusive work environment. The transition to remote work has unlocked unprecedented opportunities for organizations to tap into a global talent pool. Additionally, studies have shown that remote workers demonstrate higher productivity levels compared to their in-office counterparts. This paradigm shift in workplace dynamics is reshaping how we think about work-life balance and organizational culture.`,
      },
      {
        id: 'research',
        label: 'Research Summary',
        text: `This comprehensive literature review examines the multifaceted impact of climate change on global agricultural productivity. The analysis encompasses 47 peer-reviewed studies published between 2020 and 2025, revealing several key findings. Notably, rising temperatures have led to a significant decline in crop yields across tropical regions, with an average reduction of 8.3% per decade. Furthermore, changes in precipitation patterns have exacerbated water scarcity in arid and semi-arid zones, subsequently affecting irrigation-dependent farming systems. The evidence underscores the urgent need for innovative adaptation strategies, including the development of heat-resistant crop varieties and the implementation of precision agriculture techniques to optimize resource utilization.`,
      },
      {
        id: 'persuasive',
        label: 'Persuasive Argument',
        text: `The adoption of renewable energy sources is not merely an environmental imperative but a robust economic opportunity that nations cannot afford to overlook. Solar and wind energy technologies have achieved remarkable cost reductions, making them increasingly competitive with traditional fossil fuels. Moreover, the transition to clean energy has the potential to create millions of new jobs, thereby stimulating economic growth while simultaneously addressing the pressing challenge of climate change. It should be mentioned that countries at the forefront of renewable energy adoption have already begun to reap substantial economic benefits, positioning themselves as leaders in the emerging green economy. The evidence clearly demonstrates that investing in sustainable energy infrastructure is both a prudent fiscal decision and a moral obligation.`,
      },
    ];

    return res.json({ code: Code.Success, data: SAMPLE_TEXTS });
  });
```

- [ ] **Step 4: Verify the backend compiles**

Run: `cd backend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/routes/humanize.ts
git commit -m "feat: update humanize routes for multi-agent pipeline

SSE route now uses humanizePipeline with stage callbacks.
Added /run-sync endpoint for queue worker integration.
Added /samples endpoint with 4 AI-sounding sample texts."
```

---

### Task 5: Update Frontend — SSE Handler and Sample Texts

**Files:**
- Modify: `frontend/components/humanizer/HumBoard.tsx`
- Modify: `frontend/components/humanizer/InputPane.tsx`
- Modify: `frontend/store/slices/humanizerSlice.ts`

- [ ] **Step 1: Add currentStage to humanizer Redux slice**

In `frontend/store/slices/humanizerSlice.ts`, add `currentStage` to the state so the UI can show pipeline progress:

Add to `HumanizerState` interface:
```typescript
  currentStage: string;
```

Add to `initialState`:
```typescript
  currentStage: '',
```

Add a new reducer:
```typescript
    setCurrentStage(state, action: PayloadAction<string>) {
      state.currentStage = action.payload;
    },
```

Update the `resetOutput` reducer to also reset stage:
```typescript
    resetOutput(state) {
      state.outputText = '';
      state.changes = [];
      state.aiScoreIn = 0;
      state.aiScoreOut = 0;
      state.currentJobId = null;
      state.currentStage = '';
    },
```

Export the new action:
```typescript
export const {
  setTone,
  setStrength,
  setLengthMode,
  setInputText,
  setInputSource,
  setProcessing,
  setResult,
  resetOutput,
  setCurrentStage,
} = humanizerSlice.actions;
```

- [ ] **Step 2: Update HumBoard SSE handler to handle stage events**

In `frontend/components/humanizer/HumBoard.tsx`, import `setCurrentStage`:

```typescript
import { setProcessing, setResult, resetOutput, setCurrentStage } from '@/store/slices/humanizerSlice';
```

Update the SSE event handling loop inside `handleHumanize`. In the `for (const line of lines)` loop, add handlers for the new event types:

```typescript
            if (data.type === 'done') {
              dispatch(
                setResult({
                  outputText: data.rewrittenText,
                  changes: data.changes || [],
                  aiScoreIn: data.aiScoreIn,
                  aiScoreOut: data.aiScoreOut,
                  jobId: data.jobId,
                })
              );
              dispatch(setCurrentStage(''));
              refreshBalance();
            } else if (data.type === 'stage') {
              // Decision: Show pipeline stage progress to user during multi-agent processing.
              // Stages: preprocessing, critiquing (iteration N), rewriting (iteration N).
              const stageLabel = data.iteration
                ? `${data.stage} (pass ${data.iteration})`
                : data.stage;
              dispatch(setCurrentStage(stageLabel));
            } else if (data.type === 'score') {
              dispatch(setCurrentStage(`scoring (pass ${data.iteration}: ${data.score})`));
            } else if (data.type === 'ai_score_in') {
              dispatch(setCurrentStage('analyzing input...'));
            } else if (data.type === 'error') {
              toast.error(data.message);
              dispatch(setProcessing(false));
              dispatch(setCurrentStage(''));
            }
```

Update the humanize button to show the current stage:

```typescript
        <button
          onClick={handleHumanize}
          disabled={isProcessing || !inputText.trim()}
          className="px-8 py-3 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary-dark transition disabled:opacity-50 shadow-sm"
        >
          {isProcessing ? `Humanizing... ${currentStage}` : 'Humanize'}
        </button>
```

Add `currentStage` to the selector:

```typescript
  const { inputText, tone, strength, lengthMode, isProcessing, outputText, currentStage } = useSelector(
    (s: RootState) => s.humanizer
  );
```

- [ ] **Step 3: Add sample text buttons to InputPane**

In `frontend/components/humanizer/InputPane.tsx`, add sample text chips. Add state and a fetch for samples:

```typescript
import { useEffect, useState } from 'react';
```

Inside the `InputPane` component, add after the existing `useState` calls:

```typescript
  const [samples, setSamples] = useState<Array<{ id: string; label: string; text: string }>>([]);

  useEffect(() => {
    // Decision: Fetch sample texts once on mount for the humanizer demo experience.
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/humanize/samples`)
      .then((r) => r.json())
      .then((res) => {
        if (res.code === 1) setSamples(res.data);
      })
      .catch(() => {});
  }, []);
```

Add the sample buttons inside the content area, right before the `<textarea>`. Show them only when the textarea is empty:

```typescript
        {inputSource === 'paste' && (
          <>
            {!inputText && samples.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {samples.map((sample) => (
                  <button
                    key={sample.id}
                    onClick={() => dispatch(setInputText(sample.text))}
                    className="px-3 py-1.5 text-xs rounded-lg border border-rule text-ink-muted hover:border-primary hover:text-primary transition"
                  >
                    {sample.label}
                  </button>
                ))}
              </div>
            )}
            <textarea
              value={inputText}
              onChange={(e) => dispatch(setInputText(e.target.value))}
              placeholder="Paste your text here..."
              className="w-full h-full min-h-[300px] resize-none outline-none text-sm text-ink leading-relaxed"
            />
          </>
        )}
```

Also add the import for the API URL at the top. Check if there's already an API_URL constant used in the frontend:

The `HumBoard.tsx` uses `import { API_URL } from '@/lib/core/Constants';`. Use the same import in `InputPane.tsx`:

```typescript
import { API_URL } from '@/lib/core/Constants';
```

And update the fetch to use it:

```typescript
    fetch(`${API_URL}/api/humanize/samples`)
```

- [ ] **Step 4: Commit**

```bash
git add frontend/store/slices/humanizerSlice.ts frontend/components/humanizer/HumBoard.tsx frontend/components/humanizer/InputPane.tsx
git commit -m "feat: frontend support for multi-agent pipeline stages and sample texts

Show pipeline stage progress during humanization.
Add sample text buttons in InputPane for quick testing."
```

---

### Task 6: Manual End-to-End Test

**Files:** None (testing only)

- [ ] **Step 1: Start the backend**

Run: `cd backend && npm run dev`
Expected: Server starts without errors. Console shows `[AIDetector] Using provider: ...`

- [ ] **Step 2: Test the samples endpoint**

Run: `curl http://localhost:3001/api/humanize/samples | jq .`
Expected: JSON with `code: 1` and `data` array of 4 sample texts.

- [ ] **Step 3: Test the sync endpoint with a sample text**

Run (replace `<TOKEN>` with a valid JWT):
```bash
curl -X POST http://localhost:3001/api/humanize/run-sync \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The rapid advancement of artificial intelligence has fundamentally transformed the landscape of modern education. Furthermore, the integration of machine learning algorithms has demonstrated significant potential.",
    "tone": "academic",
    "strength": 50,
    "lengthMode": "match",
    "access_token": "<TOKEN>"
  }' | jq .
```

Expected: JSON response with `rewrittenText`, `changes`, `aiScoreIn`, `aiScoreOut`, `tokenUsage` (with steps showing model names like `gemini-3-flash-preview` and `gpt-5.5`), `iterations`.

- [ ] **Step 4: Verify token usage structure**

In the response from step 3, check that `tokenUsage.steps` contains entries like:
```json
{
  "step": "preprocess",
  "model": "gemini-3-flash-preview",
  "iteration": 0,
  "inputTokens": <number>,
  "outputTokens": <number>
}
```

And that `totalInputTokens` and `totalOutputTokens` are the sums of all steps.

- [ ] **Step 5: Test the frontend**

Open the frontend in browser. Go to the humanizer page:
1. Verify sample text buttons appear when textarea is empty
2. Click a sample text button — text should populate
3. Click Humanize — button should show stage progress (e.g., "Humanizing... preprocessing", "Humanizing... critiquing (pass 1)")
4. Wait for completion — verify output shows with AI scores
