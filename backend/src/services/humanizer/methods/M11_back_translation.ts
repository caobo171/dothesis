// backend/src/services/humanizer/methods/M11_back_translation.ts

// M11: Back-translation. English → French (Gemini) → English (GPT). Routes
// the text through a foreign language's grammatical structure on the way
// back, breaking the LLM's per-token perplexity profile in ways the original
// rewrite cannot. DIPPER (2023) used a related technique to drop DetectGPT
// detection from 70% → 4% with no semantic damage.
//
// Two LLM calls. No anchor needed. Deterministic prompts.

import { GeminiService } from '../../ai/gemini.service';
import { OpenAIService } from '../../ai/openai.service';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const TO_FRENCH_PROMPT = `Translate the user's English text into natural, idiomatic French. Do
not summarize or paraphrase — translate. Preserve every claim. Output
strict JSON: { "translation": "<french text>" }`;

const FROM_FRENCH_PROMPT = `Translate the user's French text into natural, idiomatic English. Use
varied sentence structures and unexpected word choices where the French
allows it. Avoid robotic literal translations. Output strict JSON:
{ "translation": "<english text>" }`;

function parseTranslation(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.translation === 'string' && p.translation.trim() ? p.translation : null;
  } catch { return null; }
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];

  // E → F via Gemini. Picked for fluent French and lower cost.
  const fr = await GeminiService.chat(TO_FRENCH_PROMPT, input, {
    temperature: 0.7, maxTokens: 4096, jsonMode: true,
  });
  const french = parseTranslation(fr.text) || input;
  tokens.push({ step: 'gemini_to_french', model: 'gemini-3-flash-preview', inputTokens: fr.usage.inputTokens, outputTokens: fr.usage.outputTokens });

  // F → E via GPT. Different model on the return leg ensures the final
  // distribution is GPT's, not Gemini's — same cross-model logic that
  // helped v7 in part.
  const en = await OpenAIService.chat(FROM_FRENCH_PROMPT, french, {
    maxTokens: 4096, jsonMode: true,
  });
  const output = parseTranslation(en.text) || french;
  tokens.push({ step: 'gpt_from_french', model: 'gpt-5.5', inputTokens: en.usage.inputTokens, outputTokens: en.usage.outputTokens });

  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M11', description: 'Back-translation: English → French → English (DIPPER-style)', run });
