// backend/src/services/humanizer/methods/M0_v7_baseline.ts

// M0 = current v7 pipeline (cross-model + perturbation + self-improvement loop).
// Acts as the baseline column in the bake-off. We wrap HumanizerService.humanizePipeline
// rather than copy its body so M0 stays in lockstep with whatever ships as v7 today.

import { HumanizerService } from '../humanizer.service';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult } from './types';

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const result = await HumanizerService.humanizePipeline(input, opts.tone, opts.strength, opts.lengthMode);
  return {
    output: result.rewrittenText,
    tokenSteps: result.tokenUsage.steps.map(s => ({
      step: s.step,
      model: s.model,
      inputTokens: s.inputTokens,
      outputTokens: s.outputTokens,
    })),
  };
}

registerMethod({
  id: 'M0',
  description: 'v7 baseline: cross-model + perturbation + self-improvement loop',
  run,
});
