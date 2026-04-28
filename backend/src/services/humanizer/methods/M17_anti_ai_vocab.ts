// backend/src/services/humanizer/methods/M17_anti_ai_vocab.ts

// M17: Anti-AI-vocab post-process. Single Gemini rewrite + deterministic
// substitution table that strips the most-flagged "AI vocabulary" tells
// (utilize, facilitate, leverage, "Furthermore" at sentence start, etc.).
// Targets the exact words GPTZero highlights in its "AI Vocab" panel.
//
// Layers cleanly under any other method via M19.

import { GeminiService } from '../../ai/gemini.service';
import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.rewrittenText === 'string' && p.rewrittenText.trim() ? p.rewrittenText : null;
  } catch { return null; }
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  const draft = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });

  const output = stripAiVocab(draft);
  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M17', description: 'Anti-AI-vocab table strips utilize/facilitate/Furthermore-at-start etc.', run });
