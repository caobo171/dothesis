// backend/src/services/humanizer/methods/M20_anchor_then_adversarial.ts

// M20: Voice-anchor (M7) then real adversarial loop (M9). M7 establishes
// a strong stylistic baseline; M9 surgically rewrites any sentences that
// Sapling still flags. Most-expensive candidate (M7's 3 anchors + up to
// 4 adversarial iterations) but combines the only two methods that have
// any shot at the strict-judge problem.

import { getMethod } from './index';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  const m7 = getMethod('M7');
  const r7 = await m7.run(input, opts);
  tokens.push(...r7.tokenSteps);

  const m9 = getMethod('M9');
  const r9 = await m9.run(r7.output, opts);
  tokens.push(...r9.tokenSteps);

  return { output: r9.output, tokenSteps: tokens };
}

registerMethod({ id: 'M20', description: 'Hybrid: M7 voice-anchor → M9 real-adversarial loop', run });
