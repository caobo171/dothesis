// backend/src/services/humanizer/methods/M7_voice_anchoring.ts

// M7: Voice-Anchoring. Inject 3 paragraphs of confirmed human academic prose as
// few-shot examples; instruct the rewriter to mimic cadence, word choice, and
// punctuation rhythm. Try both anchor sets per call and pick the lower
// stylometric-score output.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stylometricScore } from '../stylometric/scorer';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');
const FORMAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim();
const CASUAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim();

const TEMPLATE = (anchor: string) => `Below are 3 paragraphs written by a human academic. Study their cadence,
sentence-length variance, word choice, and punctuation rhythm. DO NOT copy
phrases — only mimic the style. Then rewrite the user's text in that voice.

EXAMPLES (human prose):
${anchor}

Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const POLISH_TEMPLATE = (anchor: string) => `Polish the user's text to match the voice of these human-written examples.
Fix grammar; preserve sentence-length variance.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<polished>" }`;

async function genWithAnchor(input: string, anchor: string): Promise<{ text: string; tokens: MethodTokenStep[] }> {
  const tokens: MethodTokenStep[] = [];
  const a = await GeminiService.chat(TEMPLATE(anchor), input, { temperature: 0.95, maxTokens: 4096, jsonMode: true });
  tokens.push({ step: 'gemini_anchored_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  let draft = parseRewritten(a.text) || input;
  const b = await OpenAIService.chat(POLISH_TEMPLATE(anchor), draft, { maxTokens: 4096, jsonMode: true });
  tokens.push({ step: 'gpt_anchored_polish', model: 'gpt-5.5', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens });
  draft = parseRewritten(b.text) || draft;
  return { text: draft, tokens };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const [formal, casual] = await Promise.all([genWithAnchor(input, FORMAL), genWithAnchor(input, CASUAL)]);
  const fScore = stylometricScore(formal.text);
  const cScore = stylometricScore(casual.text);
  const winner = fScore <= cScore ? formal : casual;
  return { output: winner.text, tokenSteps: [...formal.tokens, ...casual.tokens] };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

registerMethod({ id: 'M7', description: 'Voice-anchoring: few-shot human prose, formal vs casual, picks lower stylometric', run });
