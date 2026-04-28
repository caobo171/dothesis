// backend/src/services/humanizer/methods/M5_n_best.ts

// M5: N-Best. Generate 5 candidate drafts in parallel with varied configs,
// then pick the lowest-stylometric-score one. The stylometric scorer is
// deterministic and free — Copyscape never runs inside this method.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stylometricScore } from '../stylometric/scorer';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { buildCrossRewritePrompt } from '../prompts/cross-rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

type Candidate = { text: string; tokens: MethodTokenStep[]; label: string };

async function genGemini(input: string, opts: MethodOptions, temperature: number, label: string): Promise<Candidate> {
  const r = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature, maxTokens: 4096, jsonMode: true,
  });
  return {
    text: parseRewritten(r.text) || input,
    tokens: [{ step: `gemini_${label}`, model: 'gemini-3-flash-preview', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens }],
    label,
  };
}

async function genGptThenGemini(input: string, opts: MethodOptions): Promise<Candidate> {
  const a = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), input, { maxTokens: 4096, jsonMode: true });
  const aText = parseRewritten(a.text) || input;
  const b = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), aText, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  return {
    text: parseRewritten(b.text) || aText,
    tokens: [
      { step: 'gpt_first', model: 'gpt-5.5', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens },
      { step: 'gemini_second', model: 'gemini-3-flash-preview', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens },
    ],
    label: 'gpt_then_gemini',
  };
}

async function genGeminiThenGpt(input: string, opts: MethodOptions): Promise<Candidate> {
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  const aText = parseRewritten(a.text) || input;
  const b = await OpenAIService.chat(buildCrossRewritePrompt(opts.tone), aText, { maxTokens: 4096, jsonMode: true });
  return {
    text: parseRewritten(b.text) || aText,
    tokens: [
      { step: 'gemini_first', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens },
      { step: 'gpt_second', model: 'gpt-5.5', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens },
    ],
    label: 'gemini_then_gpt',
  };
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const candidates = await Promise.all([
    genGemini(input, opts, 0.7, 'temp07'),
    genGemini(input, opts, 0.9, 'temp09'),
    genGemini(input, opts, 1.1, 'temp11'),
    genGptThenGemini(input, opts),
    genGeminiThenGpt(input, opts),
  ]);

  // Pick lowest stylometric score (more human-like)
  let best = candidates[0];
  let bestScore = stylometricScore(best.text);
  for (const c of candidates.slice(1)) {
    const s = stylometricScore(c.text);
    if (s < bestScore) { best = c; bestScore = s; }
  }

  // Aggregate tokens from all candidates so cost is reported honestly
  const allTokens = candidates.flatMap(c => c.tokens);

  return { output: best.text, tokenSteps: allTokens };
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

registerMethod({ id: 'M5', description: 'N-best (5 drafts in parallel) ranked by stylometric scorer', run });
