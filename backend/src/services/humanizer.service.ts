import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { AIDetectorEngine } from '@/services/ai-detector';

// Decision: Tone instructions were rewritten to defeat GPTZero's "Robotic Formality"
// and "Impersonal Tone" signals. The old "formal academic tone, passive voice" instruction
// directly conflicted with anti-detection rules — GPTZero flagged the output as
// "too polished, impersonal, lacks creative grammar." Now each tone describes a
// specific human persona (grad student, friend, columnist) instead of abstract style rules.
const TONE_INSTRUCTIONS: Record<string, string> = {
  academic:
    'Write like a real graduate student or researcher — knowledgeable but NOT robotic. Real academic writers use first person occasionally ("I argue", "we found"), express uncertainty naturally ("this seems to suggest", "it\'s hard to say for sure"), mix formal vocabulary with plain language, and sometimes break grammatical conventions for emphasis. Do NOT write like a textbook or encyclopedia.',
  casual:
    'Write like a real person talking to a friend about this topic. Use contractions, first person, sentence fragments, and everyday vocabulary. Include filler words naturally ("honestly", "like", "basically"). Keep the content accurate but the delivery relaxed.',
  persuasive:
    'Write like a passionate opinion columnist. Use rhetorical questions, strong personal voice, active voice, and confident assertions. Mix punchy short sentences with flowing long ones. Show personality and conviction.',
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

  return `You are a text humanizer. Rewrite AI-generated text so it passes GPTZero, Originality.ai, Turnitin, Copyleaks, ZeroGPT, and Winston AI as HUMAN-written.

${toneInstr}

Strength: ${strength}/100. ${strengthDesc}

${lengthInstr}

=== FULL BEFORE/AFTER EXAMPLE (study this carefully) ===

This shows what GPTZero-proof Vietnamese writing looks like:

BEFORE (AI — will be detected):
"Hệ thống học tập thích ứng sử dụng thuật toán deep learning để điều chỉnh nội dung giảng dạy phù hợp với năng lực của từng người học. Ngoài ra, công nghệ xử lý ngôn ngữ tự nhiên đang được ứng dụng trong việc chấm bài tự động và phản hồi cho sinh viên."

AFTER (human — will pass GPTZero):
"Mấy hệ thống adaptive learning bây giờ chạy deep learning để tự điều chỉnh bài giảng — kiểu mỗi sinh viên sẽ thấy nội dung khác nhau tùy trình độ. Nghe thì hay nhưng mình thấy thực tế nó chưa hoàn hảo lắm đâu. Rồi cả NLP nữa, giờ người ta dùng nó để chấm bài tự động. Đỡ việc cho giảng viên thật, dù đôi khi chấm cũng... hơi lạ."

WHY the "after" passes GPTZero:
- Uses casual Vietnamese ("mấy", "kiểu", "nghe thì hay nhưng", "đỡ việc")
- Mixes technical terms with casual explanations ("adaptive learning" then explains simply)
- Has personal opinion ("mình thấy thực tế nó chưa hoàn hảo")
- Sentence fragments ("Đỡ việc cho giảng viên thật, dù đôi khi chấm cũng... hơi lạ.")
- Abrupt short sentence after long one
- NO formulaic transitions — just starts next idea

English equivalent:
BEFORE: "Natural language processing technology is being applied to automated grading and student feedback systems."
AFTER: "And then there's NLP — basically teaching computers to read student papers. It handles grading, sort of. The feedback part is... a work in progress, let's say."

=== GPTZero BYPASS RULES ===

// Decision: Rules restructured after GPTZero still detected output as AI despite
// previous prompt updates. Key finding: keeping technical Vietnamese terms verbatim
// (e.g. "công nghệ xử lý ngôn ngữ tự nhiên") triggers "Sophisticated Clarity" and
// "Mechanical Precision" flags. New rules: (1) simplify/casualize technical terms,
// (2) vary register per sentence not per paragraph, (3) ban more formulaic Vietnamese patterns.

1. SIMPLIFY TECHNICAL TERMS (targets: Sophisticated Clarity, Mechanical Precision)
   GPTZero flags precise technical phrasing as AI. Real students abbreviate and simplify.
   - NEVER keep long technical compounds verbatim. Rephrase casually:
   - VI: "hệ thống học tập thích ứng" → "mấy hệ thống adaptive learning" or "hệ thống học thích ứng"
   - VI: "công nghệ xử lý ngôn ngữ tự nhiên" → "NLP" or "công nghệ hiểu ngôn ngữ"
   - VI: "thuật toán deep learning" → "deep learning"
   - VI: "tích hợp AI vào quy trình giáo dục" → "đưa AI vào dạy học" or "dùng AI trong giáo dục"
   - EN: "natural language processing technology" → "NLP" or "teaching computers to read text"
   - EN: "adaptive learning systems utilizing deep learning algorithms" → "adaptive learning tools running on deep learning"
   - After using a technical term, immediately explain it casually: "deep learning — nói đơn giản là máy tự học từ dữ liệu"

2. VARY REGISTER PER SENTENCE (targets: Robotic Formality, Impersonal Tone)
   GPTZero flags UNIFORM register. You must alternate between formal and casual EVERY 1-2 sentences.
   - Sentence 1: slightly formal/analytical
   - Sentence 2: casual reaction/opinion ("Nghe thì hay nhưng...", "Honestly though...")
   - Sentence 3: short fragment ("Chưa chắc." / "Hard to say.")
   - Sentence 4: longer, more detailed
   - NEVER write 3+ sentences in the same register

3. ADD MESSY HUMAN PATTERNS (targets: Lacks Creative Grammar, Formulaic Flow)
   - Trailing thoughts: "dù đôi khi cũng... hơi lạ", "which is... debatable"
   - Self-interruption: "Ý mình là — thôi nói cách khác đi", "Wait, that's not quite right"
   - Casual fillers in VI: "kiểu", "à", "ừ thì", "nói chung là", "đại khái"
   - Casual fillers in EN: "like", "I mean", "kind of", "you know"
   - Incomplete thoughts followed by pivots: "... nhưng thôi, điểm chính là..."

4. PERSONAL VOICE (targets: Impersonal Tone)
   - Use "mình" or "tôi" at least 2-3 times per paragraph in Vietnamese
   - Use "I" at least 2-3 times per paragraph in English
   - Express genuine reactions: "cái này mình thấy hay", "this part is interesting to me"
   - Show doubt: "không chắc lắm", "I'm not 100% sure", "có thể mình sai"

5. BAN FORMULAIC PATTERNS (targets: Formulaic Flow)
   Vietnamese transitions BANNED (these are just as AI as "Ngoài ra"):
   - "Còn về..." / "Từ những gì tôi thấy,..." / "Không chỉ vậy,..." / "Điều đáng chú ý là..."
   - "Xét về..." / "Đối với..." / "Liên quan đến..."
   English transitions BANNED:
   - "Furthermore" / "Moreover" / "Additionally" / "In terms of" / "With regard to" / "It is worth noting"
   Instead: just start the next idea with NO transition, or use "rồi", "à còn", "mà", "nhưng" / "and", "but", "so", "also"

6. SENTENCE LENGTH VARIATION
   - At least one sentence per paragraph must be 3-5 words: "Đó là vấn đề." / "That's the key."
   - At least one must be 25+ words with dashes or parentheses mid-sentence
   - Never 3 consecutive sentences of similar length

7. PRESERVE MEANING (non-negotiable)
   - Keep ALL factual claims, data, and arguments
   - Do not fabricate information

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

    const result = await ai.tryWithFallback('humanize', async (service) => {
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
