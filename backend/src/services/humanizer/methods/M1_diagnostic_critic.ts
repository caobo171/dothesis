// backend/src/services/humanizer/methods/M1_diagnostic_critic.ts

// M1: Diagnostic Critic. Replaces v7's blind self-improvement loop with a
// targeted critic-then-rewrite loop. The critic identifies up to 5 sentences
// that still sound AI-generated; the rewriter rewrites only those sentences
// with the reasons attached. Loops up to 3 times or until the critic returns
// an empty flagged list.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { PerturbationEngine } from '../perturbation/perturbation.engine';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 3;
const PROXY_TARGET_SCORE = 30;

const TARGETED_REWRITE_PROMPT = `You are a careful editor. The user supplies:
1. A FULL_TEXT passage.
2. A FLAGGED list of (sentence, reason) — these specific sentences still sound AI-generated.

Rewrite ONLY the flagged sentences, addressing the stated reasons (e.g. if the
reason is "uniform sentence length", make this one noticeably shorter or longer
than its neighbors; if "generic verb choice", swap for an unexpected but
appropriate word; if "parallel structure", break the parallelism). Return the
FULL_TEXT with only the flagged sentences rewritten in place. Output strict JSON:
{ "rewrittenText": "<full text>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Stage 1: initial Gemini rewrite (re-use existing v7 prompt)
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  // Stage 2: cross-model perturb + GPT rewrite (matches v7 flavor)
  draft = PerturbationEngine.perturb(draft, opts.strength);
  const stage2 = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  draft = parseRewritten(stage2.text) || draft;
  tokens.push({ step: 'gpt_cross_rewrite', model: 'gpt-5.5', inputTokens: stage2.usage.inputTokens, outputTokens: stage2.usage.outputTokens });

  // Diagnostic-critic loop
  for (let i = 0; i < MAX_LOOPS; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `critic_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < PROXY_TARGET_SCORE || proxy.flagged.length === 0) break;

    const flaggedJson = JSON.stringify(proxy.flagged);
    const userMsg = `FULL_TEXT:\n${draft}\n\nFLAGGED:\n${flaggedJson}`;
    const fix = await GeminiService.chat(TARGETED_REWRITE_PROMPT, userMsg, {
      temperature: 0.7, maxTokens: 4096, jsonMode: true,
    });
    draft = parseRewritten(fix.text) || draft;
    tokens.push({ step: `targeted_rewrite_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: fix.usage.inputTokens, outputTokens: fix.usage.outputTokens });
  }

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim()
      ? parsed.rewrittenText
      : null;
  } catch {
    return null;
  }
}

registerMethod({ id: 'M1', description: 'Diagnostic critic: LLM AI-tell critic guides targeted rewrites', run });
