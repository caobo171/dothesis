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

// Side-effect imports register the methods. Add new methods here as they land.
import './M0_v7_baseline';
import './M7_voice_anchoring';
// M7 won the v8 bake-off (mean Copyscape drop 57 vs 16.6 for M0). The other
// candidates (M1-M6, M8) live in their experiment branches but are not
// imported in production.

export type { HumanizerMethod, MethodOptions, MethodResult, BenchRecord, MethodTokenStep } from './types';
