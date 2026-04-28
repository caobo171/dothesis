// backend/src/services/humanizer/methods/M15_anchor_then_backtrans.ts

// M15: Voice-anchor (M7) then back-translate (M11). The rationale: M7 wins
// the bake-off because it gives the rewriter a concrete style target;
// back-translation breaks any residual LLM token-distribution fingerprint
// without disturbing the anchored voice. Two attacks, layered.

import { getMethod } from './index';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Stage 1 — anchored rewrite via M7.
  const m7 = getMethod('M7');
  const r7 = await m7.run(input, opts);
  tokens.push(...r7.tokenSteps);

  // Stage 2 — back-translation via M11.
  const m11 = getMethod('M11');
  const r11 = await m11.run(r7.output, opts);
  tokens.push(...r11.tokenSteps);

  return { output: r11.output, tokenSteps: tokens };
}

registerMethod({ id: 'M15', description: 'Hybrid: M7 voice-anchor → M11 back-translate', run });
