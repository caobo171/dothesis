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
// v9 candidates — second wave after Sapling/GPTZero exposed v8's overfit
// to Copyscape. Mix of new mechanisms (back-translation, real adversarial
// loop) and post-processors (anti-AI-vocab, disfluency).
import './M9_real_adversarial';
import './M11_back_translation';
import './M12_disfluency';
import './M15_anchor_then_backtrans';
import './M16_first_person';
import './M17_anti_ai_vocab';
import './M18_anchor_mixing';
import './M19_strip_then_anchor';
import './M20_anchor_then_adversarial';
// v10 candidate — replaces M7's deterministic stylometric anchor picker
// with an LLM router. Cheaper than M19 (3 LLM calls vs 8) and avoids the
// case where the stylometric scorer picks an anchor whose features look
// "human" but whose register doesn't match the input.
import './M21_router_anchor';
// v11 candidate — layers M21's router-picked anchor with M11's back-translation
// to attack residual LLM token-distribution after the anchor mimicry. Built to
// break the v11.1 plateau on register-mismatched hard cases (argument, memo,
// how-to, long essay) without using Sapling-in-pipeline.
import './M22_router_then_backtrans';
// v12 candidate — layers four mechanically-measurable rewrite rules
// (hedging, fronted-clause openings, no-expansion, anti-X-and-Y) on
// top of M21's anchor pipeline, with a deterministic compliance critic
// that triggers one revision pass on violations.
import './M23_rules_critic_anchor';
// v12 follow-up — M23 minus the critic + revision step. Tests whether the
// rules-in-prompt alone deliver M23's wins without the revision call's
// variance (which catastrophically regressed T2 and T6 in the v12 bench).
import './M24_rules_no_critic';
// v13 candidate — inverse of M23. The Biber MDA diagnostic on T1-T12
// showed the failing registers are OVER-involved (high modals,
// contractions, 2nd-person, demonstratives), not under-hedged. M25
// strips those features instead of adding them.
import './M25_deinvolve_anchor';
// v13 candidate (two-stage). De-involve preprocessing LLM call BEFORE
// the M21 anchor pipeline. Separates concerns: the preprocessing
// removes involvement-register features, then M21's anchor mimicry runs
// unmodified on the cleaner input. Avoids the prompt-conflict failure
// mode that broke M23/M24/M25 (rules in the rewrite prompt erode the
// anchor voice).
import './M26_deinvolve_then_anchor';

export type { HumanizerMethod, MethodOptions, MethodResult, BenchRecord, MethodTokenStep } from './types';
