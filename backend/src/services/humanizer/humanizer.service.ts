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
  iteration: number;  // 1 for base pipeline; 2-4 for extra iterations from the self-improvement loop
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
  iterations: number; // 1 for the base pipeline + N extra iterations from the self-improvement loop (1-4 total)
};

function parseRewriteJson(raw: string): { rewrittenText: string; changes: any[] } {
  // Strip markdown code fences that some model configurations emit despite jsonMode.
  // Without this, a fenced JSON block flows into the next stage as raw text.
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    // Use stripped (not raw) as fallback so a missing rewrittenText still produces clean text.
    // Empty-string check: parsed.rewrittenText being '' is falsy; trim() catches whitespace-only.
    const text = parsed.rewrittenText?.trim() ? parsed.rewrittenText : stripped;
    return {
      rewrittenText: text,
      changes: parsed.changes || [],
    };
  } catch {
    return { rewrittenText: stripped, changes: [] };
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
      iteration: 1,
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
      iteration: 1,
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
      iteration: 1,
      inputTokens: stage3.usage.inputTokens,
      outputTokens: stage3.usage.outputTokens,
    });

    // --- Final score ---
    const aiScoreOut = await this.checkAiScore(finalText);
    onStage?.('score', { score: aiScoreOut });

    // --- Self-improvement loop (v7.1): iterate against Copyscape until target reached ---
    // Decision: Now that we have a real external scorer (Copyscape's aicheck), we can
    // iterate. Each iteration adds a perturbation pass + Gemini polish — cheap (~1 LLM
    // call + 1 Copyscape call per iteration). Skip extra GPT cross-rewrites here to
    // keep cost down.
    const TARGET_SCORE = 10;
    const MAX_EXTRA_ITERATIONS = 3;
    let bestScore = aiScoreOut;
    let bestText = finalText;
    let extraIterations = 0;

    while (bestScore >= TARGET_SCORE && extraIterations < MAX_EXTRA_ITERATIONS) {
      extraIterations++;
      console.log('[Humanizer v7] Iter %d: score %d >= target %d, refining...', extraIterations, bestScore, TARGET_SCORE);
      onStage?.('stage', { stage: 'iterating', iteration: extraIterations });

      // Perturb the current best text again
      const perturbedIter = PerturbationEngine.perturb(bestText, strength);

      // Polish to clean up any awkwardness
      const polishIter = await GeminiService.chat(buildPolishPrompt(), perturbedIter, {
        temperature: 0.3,
        maxTokens: 4096,
        jsonMode: true,
      });
      let { rewrittenText: iterText } = parseRewriteJson(polishIter.text);
      iterText = stripBannedCharacters(iterText);
      tokenSteps.push({
        step: 'gemini_polish',
        model: GEMINI_MODEL,
        iteration: 1 + extraIterations,
        inputTokens: polishIter.usage.inputTokens,
        outputTokens: polishIter.usage.outputTokens,
      });

      // Score
      const iterScore = await this.checkAiScore(iterText);
      console.log('[Humanizer v7] Iter %d done | score: %d', extraIterations, iterScore);
      onStage?.('score', { score: iterScore, iteration: extraIterations });

      // Track best result
      if (iterScore < bestScore) {
        bestScore = iterScore;
        bestText = iterText;
      }
    }

    // Use the best result we got across all iterations
    const finalScore = bestScore;
    const finalOutput = bestText;

    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);
    console.log('[Humanizer v7] Pipeline complete | score: %d → %d | tokens: in=%d out=%d', aiScoreIn, finalScore, totalInputTokens, totalOutputTokens);

    return {
      rewrittenText: finalOutput,
      changes: stage1Changes,
      aiScoreIn,
      aiScoreOut: finalScore,
      tokenUsage: { steps: tokenSteps, totalInputTokens, totalOutputTokens },
      iterations: 1 + extraIterations,
    };
  }

  // Credit cost formula. 1 credit per 50 words with a minimum of 2 per run.
  // Frontend mirrors this exact formula in HumBoard.tsx — keep them in lockstep.
  static calculateCredits(wordCount: number): number {
    return Math.max(2, Math.ceil(wordCount / 50));
  }
}
