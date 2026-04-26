import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { HumanizeJobModel } from '@/models/HumanizeJob';

const TONE_INSTRUCTIONS: Record<string, string> = {
  academic:
    'Write in a formal academic tone. Use discipline-appropriate vocabulary, passive voice where conventional, hedging language (e.g., "suggests", "may indicate"), and structured argumentation.',
  casual:
    'Write in a natural, conversational tone. Use contractions, first person, shorter sentences, and everyday vocabulary while keeping the content accurate.',
  persuasive:
    'Write in a compelling, persuasive tone. Use rhetorical questions, strong transitions, active voice, and confident assertions backed by evidence.',
};

const LENGTH_INSTRUCTIONS: Record<string, string> = {
  match: 'Keep the output approximately the same length as the input.',
  shorter: 'Make the output about 15% shorter than the input. Be more concise.',
  longer: 'Make the output about 15% longer. Add more detail and elaboration.',
};

function buildHumanizePrompt(tone: string, strength: number, lengthMode: string): string {
  const toneInstr = TONE_INSTRUCTIONS[tone] || TONE_INSTRUCTIONS.academic;
  const lengthInstr = LENGTH_INSTRUCTIONS[lengthMode] || LENGTH_INSTRUCTIONS.match;

  const strengthDesc =
    strength <= 30
      ? 'Make LIGHT edits only. Fix obviously robotic/AI-sounding phrases but preserve the original wording as much as possible.'
      : strength <= 70
        ? 'Make MODERATE edits. Rewrite sentences that sound AI-generated while preserving the core meaning and structure.'
        : 'Do a FULL rewrite. Completely rephrase all content to sound naturally human-written while preserving all factual claims and arguments.';

  return `You are a text humanizer. Your job is to rewrite AI-generated text so it reads as if written by a human student.

${toneInstr}

Strength level (${strength}/100): ${strengthDesc}

${lengthInstr}

IMPORTANT: Respond with valid JSON only. No markdown, no code fences. The JSON must have this structure:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": [
    { "original": "phrase from input", "replacement": "rewritten phrase", "reason": "brief reason" }
  ]
}

List every changed phrase in the changes array. If a sentence was unchanged, do not include it.`;
}

function buildAiScorePrompt(): string {
  return `You are an AI text detector. Analyze the given text and estimate how likely it is to be AI-generated.

Respond with valid JSON only:
{
  "score": <number 0-100>,
  "reasoning": "brief explanation"
}

Score guide:
0-20: Very likely human-written
21-40: Mostly human with some AI-like patterns
41-60: Uncertain / mixed
61-80: Likely AI-generated
81-100: Almost certainly AI-generated`;
}

export class HumanizerService {
  static buildSystemPrompt(tone: string, strength: number, lengthMode: string): string {
    return buildHumanizePrompt(tone, strength, lengthMode);
  }

  static buildAiScoreSystemPrompt(): string {
    return buildAiScorePrompt();
  }

  static async checkAiScore(text: string): Promise<number> {
    const ai = AIServiceManager.getInstance();
    const result = await ai.tryWithFallback('ai-score', async (service) => {
      return service.chat(buildAiScorePrompt(), text, {
        temperature: 0.3,
        jsonMode: true,
      });
    });

    try {
      const parsed = JSON.parse(result);
      return Math.min(100, Math.max(0, parsed.score));
    } catch {
      return 50;
    }
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
        temperature: 0.7,
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
        temperature: 0.7,
        maxTokens: 4096,
      });
    });
  }

  static calculateCredits(wordCount: number): number {
    return Math.max(1, Math.ceil(wordCount / 100));
  }
}
