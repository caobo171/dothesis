// backend/src/services/humanizer/methods/M21_router_anchor.ts

// M21: Router-picked single anchor + strip-AI-vocab wrap. Replaces the
// stylometric-scorer-based parallel anchor sweep (M7/M19) with a single
// up-front LLM call that classifies which anchor's register best fits
// the input. Then runs only that anchor's branch — saving ~5 LLM calls
// per humanize vs the 4-way parallel sweep, AND landing on the right
// anchor for inputs where the stylometric scorer historically picked
// poorly (T1, T3, T4 in different runs).
//
// Pipeline:
//   strip AI-vocab (deterministic)
//   → Gemini router: pick 1 anchor from 4 by register match
//   → Gemini rewrite anchored on the chosen one
//   → GPT polish anchored on the same
//   → strip AI-vocab again
//
// LLM call count: 3 (router + rewrite + polish). Vs M19: 8.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');

// Each anchor has a one-line description for the router. The router sees
// only these descriptions, not the anchor text — keeps the router prompt
// short and the picker's choice explicit. Adding a new anchor: drop a .txt,
// add an entry here.
// Each anchor advertises: WHEN to pick it (positive examples) and WHEN NOT
// to pick it (negative examples). The router got confused before because
// generic descriptions made multiple anchors look plausible. Tight rubrics
// let the router's classification be deterministic.
type AnchorDef = { id: string; desc: string; text: string };
const ANCHORS: AnchorDef[] = [
  {
    id: 'academic_formal',
    desc: 'PICK FOR: abstract analytical / expository writing on technical, philosophical, or scientific topics (transformer attention, vector search, market analysis, philosophy). Third-person, formal vocabulary. NOT FOR: personal stories, opinion essays, casual blogs.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim(),
  },
  {
    id: 'academic_casual',
    desc: 'PICK FOR: educational / explanatory writing addressed to a reader, lecture register, mid-formality. NOT FOR: pure abstract analysis (use academic_formal) or personal narrative (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim(),
  },
  {
    id: 'argumentative',
    desc: 'PICK FOR: input that argues a contested position (e.g. "why X is wrong", "we should do Y", policy debates, opinion pieces). The input takes a side. NOT FOR: neutral exposition.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'argumentative.txt'), 'utf8').trim(),
  },
  {
    id: 'user_modern',
    desc: 'PICK FOR: modern OPINION / REFLECTION about contemporary tech / work / productivity / education ("I think X is overrated", "what I learned about Y"). Generalizing claims, no specific incidents. NOT FOR: pure narrative with specific moments (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_modern.txt'), 'utf8').trim(),
  },
  {
    id: 'user_narrative',
    desc: 'PICK FOR: first-person STORY or EXPERIENCE — describing a specific moment, place, sensory detail, or event ("my experience doing X", "when I tried Y", "starting a morning routine", travel posts, blog posts about something the writer did). Contains concrete specifics. ALWAYS pick this over user_modern when the input is experiential or describes habits/routines/personal moments.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_narrative.txt'), 'utf8').trim(),
  },
];

const ROUTER_PROMPT = `You are an anchor-matcher. Given the user's INPUT_TEXT, pick exactly one of the
following style anchors whose register best matches the input. Match by:
- topic / domain (modern tech topics → modern anchors; abstract / theoretical → academic anchors)
- voice (first-person reflective → casual/modern; third-person formal → formal academic)
- argumentative stance (opinion / polemic → argumentative)

ANCHORS:
${ANCHORS.map((a) => `- ${a.id}: ${a.desc}`).join('\n')}

Output strict JSON: { "anchor": "<one of the anchor ids above>", "reason": "<short reason>" }`;

const REWRITE_TEMPLATE = (anchor: string) => `Below are paragraphs written by a real human. Study their cadence,
sentence-length variance, word choice, punctuation rhythm, and any natural
imperfections (run-ons, occasional typos, hedges, idiosyncratic phrasings).
DO NOT copy phrases — only mimic the style and rhythm. Match the register
shown in the examples.
Then rewrite the user's text in that voice.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const POLISH_TEMPLATE = (anchor: string) => `Polish the user's text to match the voice of these human-written examples.
Fix only the most jarring errors; preserve sentence-length variance and any
natural imperfections that match the examples' register.

EXAMPLES:
${anchor}

Output strict JSON: { "rewrittenText": "<polished>" }`;

function parseJsonField(raw: string, field: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p[field] === 'string' && p[field].trim() ? p[field] : null;
  } catch { return null; }
}

async function pickAnchor(input: string): Promise<{ id: string; reason: string; tokens: MethodTokenStep }> {
  const r = await GeminiService.chat(ROUTER_PROMPT, `INPUT_TEXT:\n${input}`, {
    temperature: 0.0,
    maxTokens: 1024,
    jsonMode: true,
  });
  const tokens: MethodTokenStep = {
    step: 'gemini_router',
    model: 'gemini-3-flash-preview',
    inputTokens: r.usage.inputTokens,
    outputTokens: r.usage.outputTokens,
  };
  const id = parseJsonField(r.text, 'anchor');
  const reason = parseJsonField(r.text, 'reason') ?? '';
  // Defensive default: if the router output is unparseable, fall back to
  // user_modern. It's the most permissive anchor and least likely to push
  // the rewrite into a register mismatch.
  const validIds = new Set(ANCHORS.map((a) => a.id));
  return {
    id: id && validIds.has(id) ? id : 'user_modern',
    reason,
    tokens,
  };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // 1) strip AI-vocab from input (deterministic, free)
  const cleaned = stripAiVocab(input);

  // 2) router picks the anchor
  const pick = await pickAnchor(cleaned);
  tokens.push(pick.tokens);
  const anchor = ANCHORS.find((a) => a.id === pick.id)!;

  // 3) Gemini rewrite anchored on the chosen one
  const rw = await GeminiService.chat(REWRITE_TEMPLATE(anchor.text), cleaned, {
    temperature: 0.95, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gemini_rewrite_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rw.usage.inputTokens, outputTokens: rw.usage.outputTokens });
  const draft = parseJsonField(rw.text, 'rewrittenText') || cleaned;

  // 4) GPT polish anchored on the same
  const pol = await OpenAIService.chat(POLISH_TEMPLATE(anchor.text), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gpt_polish_${pick.id}`, model: 'gpt-5.5', inputTokens: pol.usage.inputTokens, outputTokens: pol.usage.outputTokens });
  const polished = parseJsonField(pol.text, 'rewrittenText') || draft;

  // 5) strip AI-vocab from output (catches anything the LLM re-introduced)
  const output = stripAiVocab(polished);

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M21', description: 'Router picks 1 anchor (LLM), strip→rewrite→polish→strip', run });
