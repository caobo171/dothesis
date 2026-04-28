// backend/src/services/humanizer/methods/M6_sentence_surgical.ts

// M6: Sentence-Surgical. Don't rewrite already-human sentences. Get a draft,
// split into sentences, score each via a per-sentence LLM classifier
// (NOT Copyscape), rewrite only the worst 30%, stitch back, light polish.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { buildRewritePrompt } from '../prompts/rewrite.prompt';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const PER_SENTENCE_PROMPT = `Score how AI-generated EACH sentence sounds (0-10, higher = more AI).
Input: a JSON array of sentences.
Output: a JSON array of integer scores in the same order. No prose, no explanations.
Example input: ["Hello.", "I utilize quantum entanglement to facilitate workflow."]
Example output: [1, 9]`;

const SURGICAL_REWRITE_PROMPT = `Rewrite the SENTENCE in the context of the surrounding paragraph so it sounds
human. Make it noticeably different in length or rhythm from its neighbors.
Use unexpected word choices. Output strict JSON: { "rewrittenSentence": "<text>" }`;

const POLISH_PROMPT = `The user's text was edited sentence-by-sentence. Some transitions may be rough.
Smooth the transitions ONLY. Do not rewrite content. Do not regularize sentence
length. Output strict JSON: { "rewrittenText": "<smoothed>" }`;

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

async function run(input: string, opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // Initial draft
  const stage1 = await GeminiService.chat(buildRewritePrompt(opts.tone, opts.strength, opts.lengthMode), input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  let draft = parseRewritten(stage1.text) || input;
  tokens.push({ step: 'gemini_rewrite', model: 'gemini-3-flash-preview', inputTokens: stage1.usage.inputTokens, outputTokens: stage1.usage.outputTokens });

  const sentences = splitSentences(draft);
  if (sentences.length < 3) return { output: draft, tokenSteps: tokens };

  // Per-sentence scoring (single batched call)
  const scoreCall = await GeminiService.chat(PER_SENTENCE_PROMPT, JSON.stringify(sentences), {
    temperature: 0.1, maxTokens: 1024, jsonMode: true,
  });
  tokens.push({ step: 'sentence_scoring', model: 'gemini-3-flash-preview', inputTokens: scoreCall.usage.inputTokens, outputTokens: scoreCall.usage.outputTokens });
  const scores: number[] = parseScores(scoreCall.text, sentences.length);

  // Pick worst 30% (at least 1, at most 5)
  const n = Math.max(1, Math.min(5, Math.ceil(sentences.length * 0.3)));
  const worstIdx = scores
    .map((s, i) => ({ s, i }))
    .sort((a, b) => b.s - a.s)
    .slice(0, n)
    .map(x => x.i);

  // Rewrite each worst sentence in parallel with surrounding context
  const rewrites = await Promise.all(worstIdx.map(async (idx) => {
    const ctx = sentences.slice(Math.max(0, idx - 1), idx + 2).join(' ');
    const userMsg = `PARAGRAPH_CONTEXT: ${ctx}\n\nSENTENCE: ${sentences[idx]}`;
    const r = await OpenAIService.chat(SURGICAL_REWRITE_PROMPT, userMsg, { maxTokens: 256, jsonMode: true });
    tokens.push({ step: `surgical_${idx}`, model: 'gpt-5.5', inputTokens: r.usage.inputTokens, outputTokens: r.usage.outputTokens });
    const stripped = r.text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
    try {
      const parsed = JSON.parse(stripped);
      return { idx, replacement: typeof parsed.rewrittenSentence === 'string' ? parsed.rewrittenSentence : sentences[idx] };
    } catch { return { idx, replacement: sentences[idx] }; }
  }));

  for (const { idx, replacement } of rewrites) sentences[idx] = replacement;
  draft = sentences.join(' ');

  // Light polish for transitions
  const polish = await GeminiService.chat(POLISH_PROMPT, draft, { temperature: 0.3, maxTokens: 4096, jsonMode: true });
  draft = parseRewritten(polish.text) || draft;
  tokens.push({ step: 'transition_polish', model: 'gemini-3-flash-preview', inputTokens: polish.usage.inputTokens, outputTokens: polish.usage.outputTokens });

  return { output: draft, tokenSteps: tokens };
}

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return typeof parsed.rewrittenText === 'string' && parsed.rewrittenText.trim() ? parsed.rewrittenText : null;
  } catch { return null; }
}

function parseScores(raw: string, expectedLen: number): number[] {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const arr = JSON.parse(stripped);
    if (Array.isArray(arr) && arr.length === expectedLen) return arr.map(x => Number(x) || 0);
  } catch {}
  return new Array(expectedLen).fill(5);
}

registerMethod({ id: 'M6', description: 'Sentence-surgical: per-sentence scoring + targeted rewrites of worst 30%', run });
