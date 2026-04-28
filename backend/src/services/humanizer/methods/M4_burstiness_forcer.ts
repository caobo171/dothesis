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
