// backend/src/services/humanizer/methods/M8_combo.ts

// M8: Combo. Stacks the three Copyscape-free phases:
//   1. Initial Gemini rewrite + burstify (M4 phase)
//   2. Diagnostic-critic targeted rewrite loop (M1 phase, 2 iterations max)
//   3. Self-critique pass (M2 phase, 1 iteration)
//   4. Final GPT polish
//
// Empirical question: do these stack additively, or do later passes undo
// earlier gains? The bake-off will tell us.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { burstify } from '../burstify/burstify';
import { sentenceLengthSigma } from '../stylometric/scorer';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const TARGETED_PROMPT = `Rewrite ONLY the flagged sentences in FULL_TEXT, addressing each stated reason.
Output strict JSON: { "rewrittenText": "<full text with flagged sentences replaced>" }`;

const SELF_CRITIQUE_PROMPT = `Rewrite the passage. First, silently identify 3 sentences that still sound AI.
Then rewrite the whole passage fixing them. Output strict JSON: { "rewrittenText": "<revised>" }`;

const FINAL_POLISH = `Polish for grammar only. PRESERVE sentence-length variance, em dashes,
fragmented sentences, and unusual word choices. Output strict JSON: { "rewrittenText": "<polished>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Phase A — initial rewrite + burstify
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  if (sentenceLengthSigma(draft) < 8) draft = burstify(draft, { seed: 1 });

  // Phase B — diagnostic-critic targeted rewrites (max 2 iterations)
  for (let i = 0; i < 2; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `critic_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < 30 || proxy.flagged.length === 0) break;
    const userMsg = `FULL_TEXT:\n${draft}\n\nFLAGGED:\n${JSON.stringify(proxy.flagged)}`;
    const fix = await GeminiService.chat(TARGETED_PROMPT, userMsg, { temperature: 0.7, maxTokens: 4096, jsonMode: true });
    tokens.push({ step: `targeted_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: fix.usage.inputTokens, outputTokens: fix.usage.outputTokens });
    draft = parseRewritten(fix.text) || draft;
  }

  // Phase C — single self-critique pass
  const sc = await GeminiService.chat(SELF_CRITIQUE_PROMPT, draft, { temperature: 0.8, maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(sc.text) || draft;
  tokens.push({ step: 'self_critique', model: 'gemini-3-flash-preview', inputTokens: sc.usage.inputTokens, outputTokens: sc.usage.outputTokens });

  // Phase D — final GPT polish
  const p = await OpenAIService.chat(FINAL_POLISH, draft, { maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(p.text) || draft;
  tokens.push({ step: 'gpt_polish', model: 'gpt-5.5', inputTokens: p.usage.inputTokens, outputTokens: p.usage.outputTokens });

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

registerMethod({ id: 'M8', description: 'Combo: rewrite + burstify + critic loop + self-critique + polish', run });
