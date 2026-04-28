// backend/src/services/humanizer/methods/M9_real_adversarial.ts

// M9: Real Adversarial Loop. NeurIPS 2025 paper architecture, but with the
// real Sapling detector in the loop instead of the LLM proxy that M3 used.
// Earlier M3 failed because the proxy didn't predict Sapling. M9 closes
// that gap by feeding Sapling's actual score back into the rewriter.
//
// Pipeline:
//   draft = Gemini rewrite once.
//   loop ≤4×:
//     score = Sapling(draft)
//     if score < 30, break.
//     ask GPT to aggressively paraphrase, told the score and the worst lines.
//   return best draft seen so far (lowest Sapling score).
//
// Cost: ~5 Sapling calls + ~5 LLM calls per humanize. Sapling at $0.005/1K
// chars × ~1K = $0.005 per call → ~$0.025 per humanize. Still cheaper than
// Copyscape per humanize.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { SaplingProvider } from '../../ai-detector/providers/sapling.provider';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const MAX_LOOPS = 4;
const TARGET_SCORE = 30;

const ADVERSARIAL_PROMPT = `You are an aggressive paraphraser. The user supplies:
- TEXT: a draft scored as too AI-like
- SAPLING_SCORE: a 0-100 estimate from a real detector (higher = more AI)

Rewrite the TEXT to drive the score down. Prioritize:
1. LEXICAL DIVERSITY — replace generic words with unexpected, apt synonyms
2. CLAUSE REORDERING — change subject-verb-object patterns; lead with subordinate clauses sometimes
3. BURSTINESS — alternate short punchy sentences with long winding ones
4. Inject contractions and a single first-person aside if it fits

Preserve meaning. Output strict JSON: { "rewrittenText": "<paraphrased>" }`;

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.rewrittenText === 'string' && p.rewrittenText.trim() ? p.rewrittenText : null;
  } catch { return null; }
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];
  const sap = new SaplingProvider();

  // Stage 1 — initial Gemini rewrite (re-use existing v7 prompt).
  const a = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });

  // Track best result across iterations — the loop can occasionally regress,
  // and we want to return the lowest-scoring draft we ever saw.
  let bestDraft = draft;
  let bestScore = 100;

  for (let i = 0; i < MAX_LOOPS; i++) {
    let score: number;
    try { score = (await sap.analyze(draft)).score; }
    catch { break; } // detector failure: stop iterating, return best so far
    tokens.push({ step: `sapling_score_${i + 1}`, model: 'sapling', inputTokens: 0, outputTokens: 0 });

    if (score < bestScore) { bestScore = score; bestDraft = draft; }
    if (score < TARGET_SCORE) break;

    const userMsg = `TEXT:\n${draft}\n\nSAPLING_SCORE: ${score}`;
    const para = await OpenAIService.chat(ADVERSARIAL_PROMPT, userMsg, {
      maxTokens: 4096, jsonMode: true,
    });
    tokens.push({ step: `paraphrase_${i + 1}`, model: 'gpt-5.5', inputTokens: para.usage.inputTokens, outputTokens: para.usage.outputTokens });
    const next = parseRewritten(para.text);
    if (!next) break;
    draft = next;
  }

  return { output: bestDraft, tokenSteps: tokens };
}

registerMethod({ id: 'M9', description: 'Real adversarial loop with Sapling in-pipeline', run });
