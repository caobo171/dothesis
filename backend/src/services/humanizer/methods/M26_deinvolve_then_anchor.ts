// backend/src/services/humanizer/methods/M26_deinvolve_then_anchor.ts
//
// M26: two-stage architecture. A focused de-involve preprocessing LLM call
// runs BEFORE the existing M21 anchor pipeline. The de-involve has one
// job — reduce the input's involvement-register features (modals,
// demonstratives, contractions, 2nd-person, "be" as main verb) — and
// nothing else. Then M21's pipeline (router + rewrite + polish) runs
// UNCHANGED on the cleaner input.
//
// Why two stages: M23/M24/M25 all tried to combine anchor mimicry with
// explicit rules in a single rewrite prompt. The rules conflicted with
// the anchor's natural voice characteristics (Russell uses 1st-person;
// rules said no 1st-person — output became a sterile hybrid). Splitting
// the concerns lets each stage do one thing well.
//
// Pipeline (4 LLM calls — 1 more than M21):
//   strip AI-vocab (deterministic, free)
//   → Gemini de-involve preprocessing
//   → Gemini router: pick 1 anchor (same as M21)
//   → Gemini rewrite anchored on the chosen one (UNCHANGED prompt vs M21)
//   → GPT polish anchored on the same (UNCHANGED prompt vs M21)
//   → strip AI-vocab again
//
// Why inline (rather than import from M21): same rationale as M23/M24/M25.
// Avoid coupling experimental methods to production-critical M21.
//
// DRIFT WATCH: if M21's anchor descriptions, ROUTER_PROMPT, parseJsonField,
// pickAnchor, REWRITE_TEMPLATE, or POLISH_TEMPLATE change, evaluate
// whether to mirror the change here. Duplication is intentional;
// "they should match" is not enforced.
//
// Spec: docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md
//   (M26 is a v13 follow-up after the post-v12 Biber MDA diagnostic and
//   the M25 prompt-conflict analysis — see the v13 handoff for full
//   chronology after benches complete.)

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const ANCHOR_DIR = path.resolve(__dirname, '../../../../scripts/bench/anchors');

type AnchorDef = { id: string; desc: string; text: string };
const ANCHORS: AnchorDef[] = [
  {
    id: 'academic_formal',
    desc: 'PICK FOR: abstract analytical / expository writing on technical, philosophical, or scientific topics (transformer attention, vector search, market analysis, philosophy). Third-person, formal vocabulary. NOT FOR: personal stories, opinion essays, casual blogs, how-to guides.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_formal.txt'), 'utf8').trim(),
  },
  {
    id: 'academic_casual',
    desc: 'PICK FOR: educational / explanatory writing addressed to a reader, lecture register, mid-formality, news articles. NOT FOR: pure abstract analysis (use academic_formal) or personal narrative (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'academic_casual.txt'), 'utf8').trim(),
  },
  {
    id: 'argumentative',
    desc: 'PICK FOR: input that argues a contested position (e.g. "why X is wrong", "we should do Y", policy debates, opinion pieces). The input takes a side. NOT FOR: neutral exposition.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'argumentative.txt'), 'utf8').trim(),
  },
  {
    id: 'instructional',
    desc: 'PICK FOR: how-to / tutorial / instructional / business-formal / memo / policy / guidance content. The input tells someone how to do something or describes a procedure or formal announcement. NOT FOR: narrative or argument.',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'instructional.txt'), 'utf8').trim(),
  },
  {
    id: 'user_modern',
    desc: 'PICK FOR: modern OPINION / REFLECTION about contemporary tech / work / productivity / education ("I think X is overrated", "what I learned about Y"). Generalizing claims, no specific incidents. NOT FOR: pure narrative with specific moments (use user_narrative).',
    text: fs.readFileSync(path.join(ANCHOR_DIR, 'user_modern.txt'), 'utf8').trim(),
  },
  {
    id: 'user_narrative',
    desc: 'PICK FOR: first-person STORY or EXPERIENCE — describing a specific moment, place, sensory detail, or event ("my experience doing X", "when I tried Y", "starting a morning routine", travel posts, blog posts, product reviews). Contains concrete specifics. ALWAYS pick this over user_modern when the input is experiential or describes habits/routines/personal moments.',
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

// De-involve preprocessing — single-purpose. Takes raw input, outputs a
// version with reduced "involvement" register features. No anchor, no
// style mimicry. Just structural simplification preserving meaning.
const DEINVOLVE_TEMPLATE = `Rewrite the following text to reduce its "involvement register" — the
features that AI detectors flag in over-helpful prose. Apply ALL of:

1. STRIP POSSIBILITY MODALS where meaning survives. "X may be true" → "X is true". "X could happen" → "X happens". Keep modals only where genuinely load-bearing (real uncertainty about an unknown).

2. STRIP NECESSITY MODALS where meaning survives. "You should consider X" → "Consider X". "X must happen" → "X happens" if context allows.

3. REPLACE DEMONSTRATIVE PRONOUNS WITH DEFINITE ARTICLES. "This trend" → "the trend". "These results" → "the results". "That pattern" → "the pattern".

4. EXPAND ALL CONTRACTIONS. "it's" → "it is". "don't" → "do not". "won't" → "will not". No contractions in output.

5. CONVERT 2ND-PERSON ADDRESS TO IMPERSONAL. "You should X" → "X is necessary" or "One should X". "Your data" → "the data". The output should not address the reader.

6. PREFER ACTION VERBS OVER "be" + complement. "X is the cause of Y" → "X causes Y". "There is a tendency for X to Y" → "X tends to Y".

CRITICAL: preserve the input's content and meaning EXACTLY. Do NOT change topic, style, voice, or vocabulary beyond these specific transformations. This is not a rewrite for style — it is a structural simplification only.

Output strict JSON: { "rewrittenText": "<de-involved text>" }`;

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
  const validIds = new Set(ANCHORS.map((a) => a.id));
  // Defensive default on router-parse failure: academic_casual is mid-register
  // (educational/explanatory) and minimizes opposite-register mismatch on the
  // failing texts M26 targets. Matches M24/M25's fallback choice for the same
  // reasoning — both methods target the same failing registers.
  return {
    id: id && validIds.has(id) ? id : 'academic_casual',
    reason,
    tokens,
  };
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // 1) strip AI-vocab from input (deterministic, free)
  const cleaned = stripAiVocab(input);

  // 2) NEW: de-involve preprocessing — single-purpose Gemini call.
  //    Low temperature: this is a structural transformation, not creative
  //    rewriting. The output should be predictable and meaning-preserving.
  const di = await GeminiService.chat(DEINVOLVE_TEMPLATE, cleaned, {
    temperature: 0.3, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: 'gemini_deinvolve', model: 'gemini-3-flash-preview', inputTokens: di.usage.inputTokens, outputTokens: di.usage.outputTokens });
  // Fail-soft: if de-involve fails to produce parseable JSON, fall back to
  // the cleaned input. Don't break the whole pipeline on a preprocessing
  // glitch — better to ship anchor-mimicry-only than to error out.
  const deinvolved = parseJsonField(di.text, 'rewrittenText') || cleaned;

  // 3) router picks the anchor (now operating on the de-involved text)
  const pick = await pickAnchor(deinvolved);
  tokens.push(pick.tokens);
  const anchor = ANCHORS.find((a) => a.id === pick.id)!;

  // 4) Gemini rewrite anchored on the chosen one — UNCHANGED prompt vs M21
  const rw = await GeminiService.chat(REWRITE_TEMPLATE(anchor.text), deinvolved, {
    temperature: 0.95, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gemini_rewrite_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rw.usage.inputTokens, outputTokens: rw.usage.outputTokens });
  const draft = parseJsonField(rw.text, 'rewrittenText') || deinvolved;

  // 5) GPT polish anchored on the same — UNCHANGED prompt vs M21
  const pol = await OpenAIService.chat(POLISH_TEMPLATE(anchor.text), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gpt_polish_${pick.id}`, model: 'gpt-5.5', inputTokens: pol.usage.inputTokens, outputTokens: pol.usage.outputTokens });
  const polished = parseJsonField(pol.text, 'rewrittenText') || draft;

  // 6) strip AI-vocab from output
  const output = stripAiVocab(polished);

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M26', description: 'De-involve preprocess (1 call) + M21 anchor pipeline (unchanged)', run });
