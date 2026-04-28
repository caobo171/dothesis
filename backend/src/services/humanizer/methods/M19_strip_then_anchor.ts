// backend/src/services/humanizer/methods/M19_strip_then_anchor.ts

// M19: Anti-AI-vocab pre-process, then voice-anchor (M7). The vocabulary
// stripper removes the most obvious surface tells before M7 mimics period
// prose, so the model has fewer "Furthermore"/"utilize"/"pivotal role"
// landmarks to anchor onto when imitating. Theory: the period-anchor's
// stylistic transfer works better when the input doesn't contain modern AI
// clichés that pull the rewrite back toward the AI distribution.

import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { getMethod } from './index';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  // Pre-process: strip AI vocabulary from the *input* before M7 sees it.
  const cleaned = stripAiVocab(input);
  const m7 = getMethod('M7');
  const r = await m7.run(cleaned, opts);
  // Belt-and-suspenders: also strip the *output* in case M7's rewrites
  // re-introduced any of the flagged terms.
  const output = stripAiVocab(r.output);
  const tokens: MethodTokenStep[] = r.tokenSteps;
  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M19', description: 'Strip AI-vocab → M7 voice-anchor → strip AI-vocab again', run });
