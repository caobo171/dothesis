// backend/src/services/humanizer/methods/M16_first_person.ts

// M16: First-person reframe. Convert detached third-person prose into
// reflective first-person ("I argue that…", "what strikes me is…").
// Bet: detector training corpora skew heavily toward third-person formal
// writing because that's what AI generates. First-person reflection is
// rarer in the AI distribution and more common in genuine human prose.

import { GeminiService } from '../../ai/gemini.service';
import { registerMethod } from './index';
import type { MethodOptions, MethodResult, MethodTokenStep } from './types';

const SYSTEM_PROMPT = `Rewrite the user's text as a first-person reflective essay. Use:
- "I think", "I'd argue", "as I read it", "what strikes me is"
- Personal stake: speak as a writer engaging with the topic, not an
  encyclopedia describing it
- Vary sentence length aggressively
- Keep contractions where they fit

Preserve every factual claim and example from the original. Output strict
JSON: { "rewrittenText": "<text>" }`;

function parseRewritten(raw: string): string | null {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const p = JSON.parse(stripped);
    return typeof p.rewrittenText === 'string' && p.rewrittenText.trim() ? p.rewrittenText : null;
  } catch { return null; }
}

async function run(input: string, _opts: MethodOptions): Promise<MethodResult> {
  const tokens: MethodTokenStep[] = [];
  const a = await GeminiService.chat(SYSTEM_PROMPT, input, {
    temperature: 0.9, maxTokens: 4096, jsonMode: true,
  });
  const output = parseRewritten(a.text) || input;
  tokens.push({ step: 'gemini_first_person', model: 'gemini-3-flash-preview', inputTokens: a.usage.inputTokens, outputTokens: a.usage.outputTokens });
  return { output, tokenSteps: tokens };
}

registerMethod({ id: 'M16', description: 'First-person reframe: convert third-person formal to reflective first-person', run });
