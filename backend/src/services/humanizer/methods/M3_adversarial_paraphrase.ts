// backend/src/services/humanizer/methods/M3_adversarial_paraphrase.ts

// M3: Adversarial Paraphrase. Loop: proxy scores draft → if score >= threshold,
// GPT paraphrases AGGRESSIVELY with the proxy's flagged_phrases as targets.
// Each iteration is told its previous proxy score so it knows whether progress
// was made. Inspired by NeurIPS 2025 Adversarial Paraphrasing (arxiv 2506.07001),
// but with an LLM proxy in place of the real detector — Copyscape never runs
// inside this pipeline.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { aiLikelihoodProxy } from '../critic/ai_likelihood_proxy';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 4;
const PROXY_TARGET = 30;

const ADVERSARIAL_PROMPT = `You are an aggressive paraphraser. The user supplies:
- TEXT: the current draft
- PROXY_SCORE: a 0-100 estimate of how AI-generated it sounds (higher = worse)
- FLAGGED: phrases that triggered the proxy

Rewrite the TEXT to drive the score down. Prioritize:
1. LEXICAL DIVERSITY — replace generic words with unexpected but apt synonyms
2. CLAUSE REORDERING — change subject-verb-object patterns; lead with subordinate clauses sometimes
3. BURSTINESS — alternate short punchy sentences with long winding ones
4. Fix every FLAGGED phrase

Preserve meaning. Output strict JSON: { "rewrittenText": "<paraphrased text>" }`;

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial Gemini draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  let lastScore = 100;
  for (let i = 0; i < MAX_LOOPS; i++) {
    const proxy = await aiLikelihoodProxy(draft);
    tokens.push({ step: `proxy_${i+1}`, model: 'gemini-3-flash-preview', inputTokens: proxy.usage.inputTokens, outputTokens: proxy.usage.outputTokens });
    if (proxy.score < PROXY_TARGET) break;
    if (proxy.score >= lastScore && i > 0) break; // stop if no progress
    lastScore = proxy.score;

    const userMsg = `TEXT:\n${draft}\n\nPROXY_SCORE: ${proxy.score}\n\nFLAGGED:\n${JSON.stringify(proxy.flagged)}`;
    const para = await OpenAIService.chat(ADVERSARIAL_PROMPT, userMsg, {
      maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `paraphrase_${i+1}`, model: 'gpt-5.5', inputTokens: para.usage.inputTokens, outputTokens: para.usage.outputTokens });
    const next = parseRewritten(para.text);
    if (!next) break;
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

registerMethod({ id: 'M3', description: 'Adversarial paraphrase guided by LLM AI-likelihood proxy', run });
