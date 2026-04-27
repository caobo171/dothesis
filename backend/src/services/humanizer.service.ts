import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { GeminiService } from '@/services/ai/gemini.service';
import { OpenAIService } from '@/services/ai/openai.service';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { AIDetectorEngine } from '@/services/ai-detector';

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

// Decision (v4): Switched from rule-based to persona-based tone instructions.
// Previous versions gave 8+ explicit rules which the LLM followed UNIFORMLY,
// creating new detectable patterns. GPTZero flagged "Artificial Simplicity",
// "Rigid Guidance", "Predictable Syntax" — all caused by uniform rule-following.
// Now each tone defines a specific person with naturally varied writing habits.
const TONE_INSTRUCTIONS: Record<string, string> = {
  academic:
    'You are a 28-year-old PhD candidate who genuinely cares about this topic. You write well but imperfectly — sometimes your sentences get too long because you\'re excited about an idea, sometimes you cut yourself short. You mix technical analysis with personal observations. You\'ve read a lot about this subject and have opinions, but you also know where you might be wrong.',
  casual:
    'You are a smart college senior explaining this topic to a classmate over coffee. You know the material but you don\'t perform knowledge — you just talk naturally. Sometimes you go on tangents, sometimes you oversimplify, sometimes you say something surprisingly insightful.',
  persuasive:
    'You are an experienced journalist writing an opinion piece. You have a clear point of view but you\'re intellectually honest about counterarguments. Your writing has rhythm — you build momentum then pause for effect. You use concrete examples and analogies, not abstractions.',
};

const LENGTH_INSTRUCTIONS: Record<string, string> = {
  match: 'Keep the output approximately the same length as the input.',
  shorter: 'Make the output about 15% shorter than the input. Be more concise.',
  longer: 'Make the output about 15% longer. Add more detail and elaboration.',
};

function buildHumanizePrompt(tone: string, strength: number, lengthMode: string): string {
  const toneInstr = TONE_INSTRUCTIONS[tone] || TONE_INSTRUCTIONS.academic;
  const lengthInstr = LENGTH_INSTRUCTIONS[lengthMode] || LENGTH_INSTRUCTIONS.match;

  // Decision: Strength 31-70 was changed from "preserve structure" to "MUST restructure"
  // because the old wording caused LLMs to only do lazy word swaps (e.g. "các" → "những"),
  // which produced only -6% score drops. GPTZero still detected these as AI.
  const strengthDesc =
    strength <= 30
      ? 'Make LIGHT edits. Fix the most obvious AI-sounding phrases, add some sentence length variation, and remove blatant AI transitions. Keep most of the original wording.'
      : strength <= 70
        ? 'Make SUBSTANTIAL edits. You MUST restructure sentences — do NOT just swap individual words. Split long sentences into short+long pairs. Merge short sentences. Change sentence order within paragraphs. Replace AI transitions with natural flow. Add hedging and human voice. Every sentence should read noticeably different from the original.'
        : 'Do a COMPLETE rewrite. Rewrite every sentence from scratch as if you were a human expert writing about this topic for the first time. The output should share zero sentence structures with the input while preserving all facts and arguments.';

  // Decision (v4): Switched from rule-based (8 explicit rules) to principle-based (3 principles).
  // Rule-heavy prompts made the LLM follow rules UNIFORMLY, creating new detectable patterns.
  // GPTZero flagged "Artificial Simplicity" (too casual), "Predictable Syntax" (same structures),
  // "Rigid Guidance" (consistent style). New approach: unpredictability as core principle.
  return `${toneInstr}

Rewrite the text below in your own voice. ${strengthDesc}

${lengthInstr}

=== THREE PRINCIPLES (internalize these, don't follow mechanically) ===

1. UNPREDICTABILITY IS EVERYTHING
   AI detectors catch patterns. ANY pattern — formal, casual, simple, complex — if it's consistent, it's detectable. Your writing must be genuinely varied:
   - Some sentences should be long and analytical with nested clauses and dashes; others should be blunt. Three words. Done.
   - Some should use technical vocabulary precisely; the next should explain the same idea like you're texting a friend
   - Some paragraphs should be tight and logical; others should meander, go on a tangent, then circle back
   - Use different sentence structures: declarative, interrogative, exclamatory, fragmented, conditional — mix them unpredictably
   - NEVER establish a pattern and repeat it. If you used a dash in sentence 1, don't use another dash until sentence 4 or 5.

2. INTELLECTUAL DEPTH
   AI text is flat — it states facts linearly without genuine thought. Human writing shows a mind at work:
   - Question the data: "Con số 14% GDP nghe ấn tượng, nhưng tính cách nào thì ra con số đó?" / "That 14% figure sounds impressive, but how exactly are they measuring it?"
   - Use analogies and metaphors: "Kinh tế số giống sóng triều — ai chậm chân sẽ bị cuốn" / "The digital economy is like a tide — you either ride it or get swept away"
   - Bring in tangential observations: "Nói đến thanh toán online làm mình nhớ..." / "Speaking of online payments, it reminds me of..."
   - Present counterarguments: "Tuy nhiên, nhìn từ góc khác thì..." / "Then again, if you look at it from the other side..."
   - Show genuine curiosity: "Điều mình thắc mắc là..." / "What I actually wonder is..."

3. PRESERVE ALL FACTS
   Keep every factual claim, number, data point, and argument from the original. Do not invent information.

=== WHAT TO AVOID ===

These patterns are INSTANTLY detectable by GPTZero:
- Starting 3+ sentences the same way (e.g., all starting with subject-verb)
- Every sentence being roughly the same length
- Using transitions systematically ("Firstly... Secondly..." or "Còn về... Thêm vào đó...")
- Explaining things the same way each time (technical term → explanation → conclusion, repeated)
- Consistent register — either all formal OR all casual throughout
- Listing facts without reacting to them or questioning them

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

function buildAiScorePrompt(): string {
  return `You are an expert AI text detector. Analyze the text for specific linguistic markers that distinguish AI-generated writing from human writing.

Evaluate these dimensions individually (score each 0-100):

1. **Vocabulary uniformity**: AI tends to use consistent register and avoids colloquialisms, slang, or unexpected word choices. Humans mix registers and use idiosyncratic phrasing.
2. **Sentence structure variety**: AI often produces sentences of similar length and complexity with parallel constructions. Humans vary sentence length more naturally, including very short and very long sentences.
3. **Transitional patterns**: AI overuses smooth logical connectors ("Furthermore", "Additionally", "Moreover", "In addition"). Humans use fewer transitions and sometimes make abrupt topic shifts.
4. **Hedging and filler**: Humans use more filler words, self-corrections, and natural hedging ("kind of", "I think", "well"). AI hedging sounds formulaic ("it is worth noting", "it should be mentioned").
5. **Personality and voice**: Human writing has a distinctive voice with opinions, humor, or personal perspective. AI writing is polished but personality-neutral.
6. **Repetitive phrasing**: AI often repeats structural patterns across paragraphs. Look for templated sentence openings or list-like enumeration.

Respond with valid JSON only:
{
  "scores": { "vocabulary": <0-100>, "structure": <0-100>, "transitions": <0-100>, "hedging": <0-100>, "personality": <0-100>, "repetition": <0-100> },
  "score": <weighted average 0-100>,
  "reasoning": "brief explanation of key signals found"
}

Score guide: 0-20 = very human, 21-40 = mostly human, 41-60 = mixed, 61-80 = likely AI, 81-100 = almost certainly AI.
Be precise and differentiate carefully. Small phrasing changes CAN shift scores — pay close attention to word-level naturalness.`;
}

export class HumanizerService {
  static buildSystemPrompt(tone: string, strength: number, lengthMode: string): string {
    return buildHumanizePrompt(tone, strength, lengthMode);
  }

  static buildAiScoreSystemPrompt(): string {
    return buildAiScorePrompt();
  }

  static async checkAiScore(text: string): Promise<number> {
    const result = await AIDetectorEngine.detect(text);
    return result.score;
  }

  static async humanize(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string
  ): Promise<{ rewrittenText: string; changes: Array<{ original: string; replacement: string; reason: string }> }> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    // Decision: Destructure { text: result } because chat() now returns AIChatResult
    // with { text, usage } instead of a plain string. Task 3 will rewrite this method.
    const { text: result } = await ai.tryWithFallback('humanize', async (service) => {
      return service.chat(systemPrompt, text, {
        // Decision: Temperature raised from 0.7 → 0.9 to increase output creativity.
        // At 0.7 the LLM produced overly safe/polished text that GPTZero flagged as
        // "Mechanical Precision" and "Lacks Creativity". Higher temp = more variation.
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

  static async humanizeStream(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onChunk: (chunk: string) => void
  ): Promise<string> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

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

    const addTokenStep = (step: TokenStep) => {
      tokenSteps.push(step);
    };

    // --- Input AI score ---
    console.log('[Humanizer] Pipeline started | tone=%s strength=%d length=%s words=%d', tone, strength, lengthMode, text.split(/\s+/).length);
    const aiScoreIn = await this.checkAiScore(text);
    console.log('[Humanizer] Input AI score: %d', aiScoreIn);
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
    console.log('[Humanizer] Gemini preprocess done | in=%d out=%d tokens', preprocessResult.usage.inputTokens, preprocessResult.usage.outputTokens);
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
      console.log('[Humanizer] Calling GPT critic (pass %d)...', i);

      const criticPrompt = buildCriticPrompt();
      const criticResult = await OpenAIService.chat(criticPrompt, currentText, {
        temperature: 0.3,
        maxTokens: 2048,
        jsonMode: true,
      });
      console.log('[Humanizer] Critic pass %d done | in=%d out=%d tokens | issues=%s', i, criticResult.usage.inputTokens, criticResult.usage.outputTokens, (() => { try { return JSON.parse(criticResult.text).issues?.length ?? '?'; } catch { return '?'; } })());
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
      console.log('[Humanizer] Rewrite pass %d done | in=%d out=%d tokens', i, humanizerResult.usage.inputTokens, humanizerResult.usage.outputTokens);
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
      console.log('[Humanizer] Score after pass %d: %d (target < %d, best so far: %d)', i, score, TARGET_SCORE, Math.min(score, bestResult.score));
      onStage?.('score', { score, iteration: i });

      // Track best result
      if (score < bestResult.score) {
        bestResult = { text: currentText, score, changes };
      }

      // Exit if target reached
      if (score < TARGET_SCORE) {
        console.log('[Humanizer] Target reached! Exiting after %d iteration(s)', i);
        break;
      }
    }

    // Build final token usage summary
    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);

    console.log('[Humanizer] Pipeline complete | iterations=%d | score: %d → %d | tokens: in=%d out=%d', iterations, aiScoreIn, bestResult.score, totalInputTokens, totalOutputTokens);
    tokenSteps.forEach((s) => console.log('[Humanizer]   %s (iter %d) [%s] in=%d out=%d', s.step, s.iteration, s.model, s.inputTokens, s.outputTokens));

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

  // Credit cost formula. 2× the original (was 1/100 with min 1), so 1 credit
  // per 50 words with a minimum of 2 per run. Frontend mirrors this exact
  // formula in HumBoard.tsx — keep them in lockstep.
  static calculateCredits(wordCount: number): number {
    return Math.max(2, Math.ceil(wordCount / 50));
  }
}
