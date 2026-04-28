// backend/src/services/humanizer/humanizer.service.ts

// Decision (v8): humanizePipeline now delegates to M7 (voice-anchoring), which
// won the bake-off documented in bench-results/comparison.md. M7 prompts the
// LLM with 3 paragraphs of confirmed-human academic prose (Russell, James) as
// few-shot examples, runs once with each anchor, and picks the lower-stylometric
// output. Mean Copyscape drop 57 across 5 corpus texts vs 16.6 for v7 — and
// ~2× cheaper, ~4× faster.
//
// The legacy v7 cross-model + perturbation + self-improvement pipeline is
// preserved as method M0 for the bake-off baseline (see methods/M0_v7_baseline.ts).
//
// Spec:    docs/superpowers/specs/2026-04-28-humanizer-method-bakeoff-design.md
// Plan:    docs/superpowers/plans/2026-04-28-humanizer-method-bakeoff.md
// Results: bench-results/comparison.md

import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { GeminiService } from '@/services/ai/gemini.service';
import { OpenAIService } from '@/services/ai/openai.service';
import { AIDetectorEngine } from '@/services/ai-detector';
import { PerturbationEngine } from './perturbation/perturbation.engine';
import { buildRewritePrompt } from './prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from './prompts/cross-rewrite.prompt';
import { getMethod } from './methods';
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
  // Nullable: when the AI-detector provider is out of credit / unreachable,
  // we still complete the humanization and return null for the score
  // instead of throwing. Frontend should render "—" when null.
  aiScoreIn: number | null;
  aiScoreOut: number | null;
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

  // Returns null when the detector provider fails (e.g. Copyscape credit
  // exhausted, network error). Callers should treat null as "unknown" and
  // continue the pipeline rather than crash.
  static async checkAiScore(text: string): Promise<number | null> {
    try {
      const result = await AIDetectorEngine.detect(text);
      return result.score;
    } catch (e) {
      console.warn('[Humanizer] AI score check failed (continuing without score):', (e as Error).message);
      return null;
    }
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
    const wordCount = text.split(/\s+/).length;
    console.log('[Humanizer v8] Pipeline started | tone=%s strength=%d length=%s words=%d', tone, strength, lengthMode, wordCount);

    // Input AI score (Copyscape) — informational, drives the "before" badge in UI.
    const aiScoreIn = await this.checkAiScore(text);
    console.log('[Humanizer v8] Input AI score: %d', aiScoreIn);
    onStage?.('ai_score_in', { score: aiScoreIn });

    // Delegate humanization to M21 (router-picked anchor + strip-AI-vocab).
    // M21 won the v10.1 bake-off: mean Sapling drop 75 vs M7's 31, and mean
    // Copyscape drop 94 vs M7's 81. Cheaper too: 3 LLM calls per humanize
    // vs M7's 8. The router picks 1 anchor from {academic_formal,
    // academic_casual, argumentative, user_modern, user_narrative} via a
    // single low-cost Gemini call, then runs only that branch.
    onStage?.('stage', { stage: 'rewriting', step: 'voice_anchored' });
    const m21 = getMethod('M21');
    const m21Result = await m21.run(text, { tone, strength, lengthMode });
    const finalText = stripBannedCharacters(m21Result.output);

    // Output AI score (Copyscape) — drives the "after" badge in UI.
    const aiScoreOut = await this.checkAiScore(finalText);
    onStage?.('score', { score: aiScoreOut });

    // Translate M21's MethodTokenStep[] into the legacy TokenStep[] shape so
    // the existing PipelineResult contract stays unchanged. iteration=1 since
    // M21 is single-shot (router + 2 LLM calls, no loop).
    const tokenSteps: TokenStep[] = m21Result.tokenSteps.map((s) => ({
      step: s.step as any,
      model: s.model,
      iteration: 1,
      inputTokens: s.inputTokens,
      outputTokens: s.outputTokens,
    }));
    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);
    console.log('[Humanizer v8] Pipeline complete | score: %d → %d | tokens: in=%d out=%d', aiScoreIn, aiScoreOut, totalInputTokens, totalOutputTokens);

    return {
      rewrittenText: finalText,
      changes: [],
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
