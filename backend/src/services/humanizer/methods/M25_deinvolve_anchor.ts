// backend/src/services/humanizer/methods/M25_deinvolve_anchor.ts
//
// M25: M21's anchor pipeline + an explicit DE-INVOLVE rules block injected
// into the rewrite prompt. The block pushes the LLM AWAY from features
// that the v12 Biber MDA diagnostic identified as over-represented in the
// 5 failing register-types (T3, T7, T8, T9, T11): possibility/necessity
// modals, demonstrative pronouns, 2nd-person address, contractions,
// `be` as main verb, and "involved" register markers.
//
// This is the INVERSE of M23. M23 added more hedges and modals, which
// the Biber data subsequently showed are exactly the features that
// distinguish failing from passing texts. M23 catastrophically
// regressed T2 (10→100) and T6 (1→97) — almost certainly because the
// added hedges pushed already-modal-heavy inputs further into the
// failure register zone. M25 strips them instead.
//
// Pipeline (3 LLM calls — same budget as M21):
//   strip AI-vocab (deterministic, free)
//   → Gemini router: pick 1 anchor (same as M21/M23/M24)
//   → Gemini rewrite anchored on the chosen one + DE_INVOLVE_RULES_BLOCK
//   → GPT polish anchored on the same (UNCHANGED from M21)
//   → strip AI-vocab again
//
// Why inline (rather than import from M21/M23/M24): same rationale as
// M23/M24. Avoid coupling experimental methods to the production-critical
// M21 or to parallel experiments.
//
// DRIFT WATCH: if M21/M23/M24's anchor descriptions, ROUTER_PROMPT,
// parseJsonField, pickAnchor, or POLISH_TEMPLATE change, evaluate whether
// to mirror the change here. Duplication is intentional; "they should
// match" is not enforced.
//
// Spec: docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md
//   (M25 is a follow-up experiment derived from the post-v12 Biber MDA
//   diagnostic — see /tmp/biber-features.dat analysis in the handoff
//   addendum, written after M25 benches.)

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

// The de-involve rules — appended to the rewrite prompt. Pushes the LLM
// AWAY from the features the Biber MDA diagnostic identified as over-
// represented in the 5 failing registers. Each rule attacks one specific
// Biber dimension where failing > passing.
const DE_INVOLVE_RULES_BLOCK = `
ADDITIONAL REWRITE RULES — apply all six; these take precedence where they conflict with the examples' cadence:

1. STRIP POSSIBILITY MODALS. Remove "may", "might", "could", "can" where the meaning survives. "X may be true" → "X is true". "X could happen" → "X happens" or "X happened". Where the modal is genuinely load-bearing (e.g. expressing real uncertainty about an unknown future event), keep it.

2. STRIP NECESSITY MODALS. Remove "must", "should", "ought to" where the meaning survives. "You should consider X" → "Consider X" (imperative) or "Consider X" if context allows. Where the modal expresses a real obligation that would be lost without it, keep it.

3. REPLACE DEMONSTRATIVE PRONOUNS WITH DEFINITE ARTICLES. "This trend" → "the trend". "That pattern" → "the pattern". "These results" → "the results". "Those studies" → "the studies". Apply only to abstract/non-deictic references (not when "this" actually points to something physical and present).

4. EXPAND CONTRACTIONS. "it's" → "it is". "don't" → "do not". "won't" → "will not". "can't" → "cannot". "aren't" → "are not". Etc. Use the formal expanded form throughout.

5. CONVERT 2ND-PERSON ADDRESS TO IMPERSONAL. "You should X" → "X is necessary" or use the passive ("X must be done"). "Your data" → "the data". "When you Y" → "When one Y" or rephrase to remove the address. The output should not address the reader directly.

6. PREFER ACTION VERBS OVER "be" + complement. "X is the cause of Y" → "X causes Y". "There is a tendency for X to Y" → "X tends to Y". "It is the case that X" → "X". When "be" is the only natural verb (definitions, identity), keep it.
`;

const REWRITE_TEMPLATE = (anchor: string) => `Below are paragraphs written by a real human. Study their cadence,
sentence-length variance, word choice, punctuation rhythm, and any natural
imperfections (run-ons, occasional typos, hedges, idiosyncratic phrasings).
DO NOT copy phrases — only mimic the style and rhythm. Match the register
shown in the examples.
Then rewrite the user's text in that voice.

EXAMPLES:
${anchor}
${DE_INVOLVE_RULES_BLOCK}
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
  const validIds = new Set(ANCHORS.map((a) => a.id));
  // Defensive default on router-parse failure: academic_casual is mid-register
  // (educational/explanatory) and minimizes opposite-register mismatch on the
  // failing texts M25 targets (T3, T7, T8, T9, T11). Matches M24's fallback
  // choice for the same reasoning — both methods target these failing registers.
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

  // 2) router picks the anchor
  const pick = await pickAnchor(cleaned);
  tokens.push(pick.tokens);
  const anchor = ANCHORS.find((a) => a.id === pick.id)!;

  // 3) Gemini rewrite anchored on the chosen one, with de-involve rules appended
  const rw = await GeminiService.chat(REWRITE_TEMPLATE(anchor.text), cleaned, {
    temperature: 0.95, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gemini_rewrite_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rw.usage.inputTokens, outputTokens: rw.usage.outputTokens });
  const draft = parseJsonField(rw.text, 'rewrittenText') || cleaned;

  // 4) GPT polish anchored on the same (unchanged from M21)
  const pol = await OpenAIService.chat(POLISH_TEMPLATE(anchor.text), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gpt_polish_${pick.id}`, model: 'gpt-5.5', inputTokens: pol.usage.inputTokens, outputTokens: pol.usage.outputTokens });
  const polished = parseJsonField(pol.text, 'rewrittenText') || draft;

  // 5) strip AI-vocab from output
  const output = stripAiVocab(polished);

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M25', description: 'M21 anchor + de-involve rules (strip modals/contractions/2nd-person)', run });
