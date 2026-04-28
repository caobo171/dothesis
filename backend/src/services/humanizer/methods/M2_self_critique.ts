// backend/src/services/humanizer/methods/M2_self_critique.ts

// M2: Self-Critique. Same shape as M1 but the rewriter critiques its own
// previous draft (no separate critic). The model is asked first to identify
// 3-5 sentences in *its own output* that still sound AI, then to rewrite
// against that self-assessment. Repeat ≤3 times.

import { GeminiService } from '../../ai/gemini.service';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 3;

const SELF_CRITIQUE_PROMPT = `You wrote the passage below in a previous turn. Now look at it with fresh eyes
and identify 3-5 sentences that still sound AI-generated. Reasons may include:
generic word choice, uniform sentence length, parallel structure, formal connectors,
sterile punctuation. Then rewrite the WHOLE passage, fixing those specific
issues — make some sentences much shorter, others longer with multiple clauses,
swap predictable verbs for unexpected ones. Output strict JSON:
{ "critique": ["<bullet>", "..."], "rewrittenText": "<full revised passage>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  // Self-critique iterations
  for (let i = 0; i < MAX_LOOPS; i++) {
    const r = await GeminiService.chat(SELF_CRITIQUE_PROMPT, draft, {
      temperature: 0.8, maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `self_critique_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens });
    const next = parseRewritten(r.text);
    if (!next || next === draft) break;
    draft = next;
  }

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M2', description: 'Self-critique loop: model critiques its own prior draft and rewrites', run });
