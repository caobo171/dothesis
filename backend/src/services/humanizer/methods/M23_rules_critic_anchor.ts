// backend/src/services/humanizer/methods/M23_rules_critic_anchor.ts
//
// M23: M21 (router-anchor) + four mechanically-measurable rewrite rules
// injected into the Gemini rewrite prompt + a deterministic compliance
// critic that triggers ONE revision pass on rule violations.
//
// Pipeline:
//   strip AI-vocab (deterministic, free)
//   → Gemini router: pick 1 anchor (same as M21)
//   → Gemini rewrite anchored on the chosen one + four rules in the prompt
//   → deterministic rule-compliance critic
//       ├ pass → continue
//       └ fail → ONE revision call to Gemini with quantitative feedback
//   → GPT polish anchored on the same (UNCHANGED from M21)
//   → strip AI-vocab again
//
// LLM call count: 3 (best case) or 4 (revision triggered). Vs M21: 3.
//
// Why inline the anchor library + prompts rather than import from M21:
// the rewrite prompt diverges (rules appended), and importing partial
// internals from M21 would couple the production-critical M21 to an
// experimental method. Duplication is the right tradeoff here.
//
// DRIFT WATCH: if M21's anchor descriptions, ROUTER_PROMPT, parseJsonField,
// pickAnchor, or POLISH_TEMPLATE change, evaluate whether to mirror the
// change here. The duplication is intentional; "they should match" is not
// enforced.
//
// Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { stripAiVocab } from '../postprocess/anti_ai_vocab';
import { checkRuleCompliance, formatRevisionFeedback } from '../critic/rule_compliance';
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

// The four rules — appended to the rewrite prompt. Drawn from the YouTube
// humanization tutorial (see spec). Each rule is mechanically measurable
// by the rule_compliance checker, and the critic feedback (Task 1) refers
// back to these by name.
const RULES_BLOCK = `
ADDITIONAL REWRITE RULES — apply all four; these take precedence where they conflict with the examples' cadence:

1. HEDGING. Use intellectual hesitation. Replace flat factual statements with hedged ones using "appears", "seems", "may", "might", "can", "suggests", "is believed", "is suspected", "is likely", "tends to", "arguably", "presumably". Aim for at least 2 hedge tokens per 100 words.

2. SENTENCE-OPENING VARIATION. Start at least 25% of sentences with something other than the subject NP — use subordinators ("Although", "While", "Given", "Despite", "When"), present participles ("Considering", "Looking"), or fronted prepositional phrases ("In recent years,", "Across the field,", "By contrast,").

3. SIMPLIFICATION (NO EXPANSION). The output must not be more than 5% longer than the input. Cut filler — vague generalizations, surface-level qualifiers, and repeated points. If you find yourself adding rather than rewording, stop.

4. AVOID "X AND Y" TWO-ITEM LISTS. Do not chain pairs like "social and educational", "anxiety and fear", "students and teachers". Use single nouns, longer enumerations (three+ items), or rephrase. Limit two-item conjunctions to ≤ 3 per 100 words.
`;

const REWRITE_TEMPLATE = (anchor: string) => `Below are paragraphs written by a real human. Study their cadence,
sentence-length variance, word choice, punctuation rhythm, and any natural
imperfections (run-ons, occasional typos, hedges, idiosyncratic phrasings).
DO NOT copy phrases — only mimic the style and rhythm. Match the register
shown in the examples.
Then rewrite the user's text in that voice.

EXAMPLES:
${anchor}
${RULES_BLOCK}
Output strict JSON: { "rewrittenText": "<text in mimic voice>" }`;

const REVISION_TEMPLATE = (anchor: string, feedback: string) => `You previously rewrote a text in the voice of these human-written examples.
Your rewrite missed some of the explicit rules. Revise the rewrite to fix
the noted issues while preserving the original meaning AND continuing to
mimic the examples' voice.

EXAMPLES:
${anchor}

${feedback}

Output strict JSON: { "rewrittenText": "<revised text>" }`;

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
  // failing texts M23 targets (how-to, memo, argumentative). M21 uses
  // user_modern here; M23 deliberately diverges because user_modern is
  // reflective-opinion register and would hurt instructional inputs.
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

  // 3) Gemini rewrite anchored on the chosen one, with rules appended
  const rw = await GeminiService.chat(REWRITE_TEMPLATE(anchor.text), cleaned, {
    temperature: 0.95, maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gemini_rewrite_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rw.usage.inputTokens, outputTokens: rw.usage.outputTokens });
  let draft = parseJsonField(rw.text, 'rewrittenText') || cleaned;

  // 4) deterministic compliance critic — checks the four rules.
  const report = checkRuleCompliance(cleaned, draft);
  if (!report.passed) {
    // Debug aid: which rules failed? Visible in bench output AND in dev logs.
    // Bench infers revision from token-step presence, but this is for humans.
    console.log('[M23] critic fired, rules failed:', report.violations.map((v) => v.rule).join(','));
    // ONE revision call only. Bounded cost, predictable latency.
    const feedback = formatRevisionFeedback(report);
    const rev = await GeminiService.chat(REVISION_TEMPLATE(anchor.text, feedback), draft, {
      temperature: 0.85, maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `gemini_revise_${pick.id}`, model: 'gemini-3-flash-preview', inputTokens: rev.usage.inputTokens, outputTokens: rev.usage.outputTokens });
    const revised = parseJsonField(rev.text, 'rewrittenText');
    // Only adopt the revision if it parsed; otherwise keep the original draft.
    if (revised) draft = revised;
  }

  // 5) GPT polish anchored on the same (unchanged from M21)
  const pol = await OpenAIService.chat(POLISH_TEMPLATE(anchor.text), draft, {
    maxTokens: 4096, jsonMode: true,
  });
  tokens.push({ step: `gpt_polish_${pick.id}`, model: 'gpt-5.5', inputTokens: pol.usage.inputTokens, outputTokens: pol.usage.outputTokens });
  const polished = parseJsonField(pol.text, 'rewrittenText') || draft;

  // 6) strip AI-vocab from output
  const output = stripAiVocab(polished);

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M23', description: 'M21 + four rewrite rules + deterministic critic with one revision pass', run });
