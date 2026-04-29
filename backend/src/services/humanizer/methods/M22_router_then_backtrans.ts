// backend/src/services/humanizer/methods/M22_router_then_backtrans.ts

// M22: M21 (router-picked anchor + strip-AI-vocab) → M11 (back-translation).
//
// Layers two attacks: voice mimicry from a period/idiosyncratic anchor (M21),
// then English → French → English routing to break residual LLM token
// distribution (M11). Built after the v11.1 plateau showed M21 alone has
// 5 weak registers (T3 argument, T7 long essay, T8 how-to, T9 news,
// T11 memo); back-translation is a cost-bounded distribution-attack that
// doesn't need Sapling-in-loop (which the project forbids on cost grounds).
//
// Total LLM calls: 5 (router + rewrite + polish + to-french + from-french).
// Vs M21 alone: 3. Vs M19: 8. Still cheaper than M19.

import { getMethod } from './index';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Stage 1 — anchored rewrite via M21 (router picks 1 anchor).
  const m21 = getMethod('M21');
  const r21 = await m21.run(input, opts);
  tokens.push(...r21.tokenSteps);

  // Stage 2 — back-translation via M11. Routes the M21 output through
  // French grammar on the way back to English. Detectors trained on LLM
  // outputs see a different per-token perplexity profile than either
  // a pure LLM rewrite or a pure anchor mimic.
  const m11 = getMethod('M11');
  const r11 = await m11.run(r21.output, opts);
  tokens.push(...r11.tokenSteps);

  return { output: r11.output, tokenSteps: tokens };
}

registerMethod({ id: 'M22', description: 'Hybrid: M21 router-anchor → M11 back-translation', run });
