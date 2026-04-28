// backend/src/services/humanizer/methods/index.ts

// Decision: Keep the registry as a plain Map keyed by method id, populated
// via side-effect imports. Each method file calls registerMethod() at module
// top level. The harness imports './methods' to load every registered method.

import type { HumanizerMethod } from './types';

const registry = new Map<string, HumanizerMethod>();

export function registerMethod(m: HumanizerMethod): void {
  if (registry.has(m.id)) {
    throw new Error(`Method ${m.id} already registered`);
  }
  registry.set(m.id, m);
}

export function getMethod(id: string): HumanizerMethod {
  const m = registry.get(id);
  if (!m) throw new Error(`No method registered with id ${id}. Known: ${[...registry.keys()].join(',')}`);
  return m;
}

export function listMethods(): HumanizerMethod[] {
  return [...registry.values()].sort((a, b) => a.id.localeCompare(b.id));
}

// Side-effect imports register the methods.
//
// Production uses M7 (winner of the v8 bake-off; see bench-results/comparison.md).
// M1-M8 are also imported here so the bench harness can re-run any of them on
// demand against multiple judges (Copyscape, Sapling). They have no runtime
// cost unless the bench harness asks for them by id.
import './M0_v7_baseline';
import './M1_diagnostic_critic';
import './M2_self_critique';
import './M3_adversarial_paraphrase';
import './M4_burstiness_forcer';
import './M5_n_best';
import './M6_sentence_surgical';
import './M7_voice_anchoring';
import './M8_combo';

export type { HumanizerMethod, MethodOptions, MethodResult, BenchRecord, MethodTokenStep } from './types';
