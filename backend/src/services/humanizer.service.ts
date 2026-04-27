import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { AIDetectorEngine } from '@/services/ai-detector';

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

  static calculateCredits(wordCount: number): number {
    return Math.max(1, Math.ceil(wordCount / 100));
  }
}
