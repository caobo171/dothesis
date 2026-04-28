// backend/src/services/humanizer/methods/M12_disfluency.ts

// M12: Deterministic disfluency injection. Targets the "LLM is too perfect"
// signal: humans hedge, self-correct, and occasionally write fragments.
// Pure post-process applied after a single Gemini rewrite.
//
// Layered with the v7 rewrite so we get baseline fluency first; the
// disfluency pass is the only thing that distinguishes M12 from a pure
// single-shot rewrite.

import { GeminiService } from '../../ai/gemini.service';
import { injectDisfluencies } from '../postprocess/disfluency';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.rewrittenText === 'string' && p.rewrittenText.trim() ? p.rewrittenText : null;
  } catch { return null; }
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  const draft = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });

  const output = injectDisfluencies(draft, { seed: 1, rate: 0.25 });
  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M12', description: 'Disfluency injection: hedges, asides, fragments after rewrite', run });
