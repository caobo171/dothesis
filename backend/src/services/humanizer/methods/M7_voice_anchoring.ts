// backend/src/services/humanizer/methods/M7_voice_anchoring.ts

// M7: Voice-Anchoring. Inject 3 paragraphs of confirmed human prose as few-shot
// examples; instruct the rewriter to mimic cadence, word choice, and punctuation
// rhythm. Run all anchors in parallel and pick the lowest stylometric output.
//
// Anchor library (all unambiguously human):
// - academic_formal: Russell, "The Problems of Philosophy" (1912) — formal analysis
// - academic_casual: James, "Talks to Teachers" (1899) — looser lecture register
// - argumentative:   Mill,  "On Liberty" (1859) — argued opinion, polemic register
// - user_modern:     project owner's own pre-LLM writing — modern register, casual,
//                    with natural typos and run-ons that period anchors lack. The
//                    typos and grammatical imperfections ARE the value: they're the
//                    strongest "verified human" signal modern neural detectors look for.
//
// Adding more anchors here automatically extends the parallel sweep and the
// scorer-based winner selection. The cost scales linearly in the anchor count.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stylometricScore } from '../stylometric/scorer';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');

// To extend the library: drop a .txt into ANCHOR_DIR and add an entry here.
// Order doesn't matter — the stylometric scorer picks the winner.
const ANCHORS: { id: string; text: string }[] = [
  { id: 'academic_formal', text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim() },
  { id: 'academic_casual', text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim() },
  { id: 'argumentative',   text: fs.readFileSync(path.join(ANCHOR_DIR, 'argumentative.txt'),   'utf8').trim() },
  { id: 'user_modern',     text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_modern.txt'),     'utf8').trim() },
];

const TEMPLATE = (anchor: string) => `Below are paragraphs written by a real human. Study their cadence,
sentence-length variance, word choice, punctuation rhythm, and any natural
imperfections (run-ons, occasional typos, hedges, idiosyncratic phrasings).
DO NOT copy phrases — only mimic the style and rhythm. Match the register
shown in the examples (formal, casual, argumentative, etc.).
Then rewrite the user's text in that voice.

EXAMPLES (human prose — preserve their feel):
${anchor}

Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const POLISH_TEMPLATE = (anchor: string) => `Polish the user's text to match the voice of these human-written examples.
Fix only the most jarring errors; preserve sentence-length variance and
any natural imperfections that match the examples' register.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<polished>" }`;

async function genWithAnchor(input: string, anchorId: string, anchor: string): Promise<{ id: string; text: string; tokens: MethodTokenStep[] }> {
  const tokens: MethodTokenStep[] = [];
  const a = await GeminiService.chat(TEMPLATE(anchor), input, { temperature: 0.95, maxTokens: 4096, jsonMode: true });
  // Step labels include the anchor id so token reports stay readable as the
  // anchor library grows; without this all branches would log identically.
  tokens.push({ step: `gemini_anchored_${anchorId}`, model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  let draft = parseRewritten(a.text) || input;
  const b = await OpenAIService.chat(POLISH_TEMPLATE(anchor), draft, { maxTokens: 4096, jsonMode: true });
  tokens.push({ step: `gpt_polish_${anchorId}`, model: 'gpt-5.5', inputTokens: b.usage.inputTokens, outputTokens: b.usage.outputTokens });
  draft = parseRewritten(b.text) || draft;
  return { id: anchorId, text: draft, tokens };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  // Fan out one branch per anchor in parallel. Stylometric scorer (deterministic,
  // free) picks the most human-like output. The branches share no state, so
  // adding anchors only widens the sweep — never breaks anything.
  const branches = await Promise.all(
    ANCHORS.map((a) => genWithAnchor(input, a.id, a.text)),
  );
  let winner = branches[0];
  let bestScore = stylometricScore(winner.text);
  for (const b of branches.slice(1)) {
    const s = stylometricScore(b.text);
    if (s < bestScore) { winner = b; bestScore = s; }
  }
  const allTokens = branches.flatMap((b) => b.tokens);
  return { output: winner.text, tokenSteps: allTokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

registerMethod({ id: 'M7', description: 'Voice-anchoring: few-shot human prose, formal vs casual, picks lower stylometric', run });
