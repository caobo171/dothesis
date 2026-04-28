// backend/src/services/humanizer/methods/M18_anchor_mixing.ts

// M18: Anchor mixing. M7 picks the single best anchor for the whole text;
// M18 alternates anchors mid-document by splitting the input into halves
// and giving each half a different anchor, then stitching. The bet: a
// non-uniform stylometric profile is harder to fingerprint as a single
// "voice mimic" by neural detectors that learned what M7 looks like.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');
const FORMAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim();
const CASUAL = fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim();
const ARGUE  = fs.readFileSync(path.join(ANCHOR_DIR, 'argumentative.txt'),   'utf8').trim();

const TEMPLATE = (anchor: string) => `Below are paragraphs written by a human academic. Mimic their cadence,
sentence-length variance, word choice, and punctuation rhythm. DO NOT copy
phrases — only mimic the style. Rewrite the user's text in that voice.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<text>" }`;

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.rewrittenText === 'string' && p.rewrittenText.trim() ? p.rewrittenText : null;
  } catch { return null; }
}

function splitInHalf(text: string): [string, string] {
  // Sentence-aware split so we don't tear a word in half.
  const sentences = (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
  if (sentences.length < 2) return [text, ''];
  const mid = Math.ceil(sentences.length / 2);
  return [sentences.slice(0, mid).join(' '), sentences.slice(mid).join(' ')];
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];
  const [head, tail] = splitInHalf(input);
  if (!tail) {
    // Single-sentence input: fall back to one anchor (formal).
    const r = await GeminiService.chat(TEMPLATE(FORMAL), input, { temperature: 0.95, maxTokens: 4096, jsonMode: true });
    tokens.push({ step: 'gemini_formal_only', model: 'gemini-3-flash-preview', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens });
    return { output: parseRewritten(r.text) || input, tokenSteps: tokens };
  }

  // Different anchor per half. Two anchor pairs are tried in parallel
  // (formal+casual, formal+argumentative); we return whichever pair gives
  // the more stylometric variance — bake-off comparison is on the joined doc.
  const [a, b, c] = await Promise.all([
    GeminiService.chat(TEMPLATE(FORMAL), head, { temperature: 0.95, maxTokens: 4096, jsonMode: true }),
    GeminiService.chat(TEMPLATE(CASUAL), tail, { temperature: 0.95, maxTokens: 4096, jsonMode: true }),
    GeminiService.chat(TEMPLATE(ARGUE),  tail, { temperature: 0.95, maxTokens: 4096, jsonMode: true }),
  ]);
  tokens.push({ step: 'gemini_head_formal',  model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  tokens.push({ step: 'gemini_tail_casual',  model: 'gemini-3-flash-preview', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens });
  tokens.push({ step: 'gemini_tail_argue',   model: 'gemini-3-flash-preview', inputTokens: c.usage.inputTokens, outputTokens: c.usage.outputTokens });

  const headText = parseRewritten(a.text) || head;
  // Pick whichever tail anchor shifts the cadence more. We keep it simple:
  // use the one whose first sentence is longer than the other's (proxy for
  // "more stylistic shift from the head anchor"). Cheap, no judge call.
  const tailCasual = parseRewritten(b.text) || tail;
  const tailArgue  = parseRewritten(c.text) || tail;
  const firstLen = (s: string) => (s.match(/^[^.!?]+/) || [''])[0].split(/\s+/).length;
  const tailText = firstLen(tailCasual) >= firstLen(tailArgue) ? tailCasual : tailArgue;

  // Light polish to repair the seam.
  const polish = await OpenAIService.chat(
    `The user's text was written by joining two halves with different stylistic anchors.
Smooth ONLY the transition between paragraphs / mid-document — do not regularize cadence
elsewhere. Preserve all the stylistic variance. Output strict JSON: { "rewrittenText": "<text>" }`,
    `${headText}\n\n${tailText}`,
    { maxTokens: 4096, jsonMode: true },
  );
  tokens.push({ step: 'gpt_seam_polish', model: 'gpt-5.5', inputTokens: polish.usage.inputTokens, outputTokens: polish.usage.outputTokens });
  const output = parseRewritten(polish.text) || `${headText}\n\n${tailText}`;
  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M18', description: 'Anchor mixing: different anchor per half + seam polish', run });
