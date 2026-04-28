// backend/src/services/humanizer/critic/ai_likelihood_proxy.ts

// LLM-based AI-likelihood proxy. Replaces Copyscape inside the pipeline so
// methods M1, M3, M6, M8 can iterate without making external scoring calls.
// Returns a 0-100 score (higher = more AI-like) and a list of specific
// flagged sentences with reasons. The pipeline uses both: the score gates
// the loop (stop iterating once score < threshold), the flagged list tells
// the next rewrite where to focus.

import { GeminiService } from '../../ai/gemini.service';

const SYSTEM_PROMPT = `You are an AI-text-detection diagnostic. Read the user's text and judge how AI-generated it sounds based on three signals:

1. PERPLEXITY: predictable / generic word choice (e.g. "utilize", "facilitate", "delve into")
2. BURSTINESS: uniform sentence length and rhythm
3. STYLOMETRIC TELLS: parallel structures, formal connectors ("Furthermore", "Moreover"), low function-word variety, sterile punctuation

Output strict JSON with this exact shape — no prose, no markdown:
{
  "score": <0-100, where 0=clearly human, 100=clearly AI>,
  "flagged": [
    { "sentence": "<exact substring of the input>", "why": "<short reason citing one of the signals>" }
  ]
}

Flag at most 5 sentences, the worst offenders. If the text is clearly human, return score < 30 and an empty flagged array.`;

export type ProxyFlag = { sentence: string; why: string };
export type ProxyResult = {
  score: number;
  flagged: ProxyFlag[];
  usage: { inputTokens: number; outputTokens: number };
};

export function parseProxyResponse(raw: string): { score: number; flagged: ProxyFlag[] } {
  const stripped = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  try {
    const parsed = JSON.parse(stripped);
    return {
      score: typeof parsed.score === 'number' ? parsed.score : 100,
      flagged: Array.isArray(parsed.flagged) ? parsed.flagged : [],
    };
  } catch {
    return { score: 100, flagged: [] };
  }
}

export async function aiLikelihoodProxy(text: string): Promise<ProxyResult> {
  const response = await GeminiService.chat(SYSTEM_PROMPT, text, {
    temperature: 0.1,
    maxTokens: 1024,
    jsonMode: true,
  });
  const { score, flagged } = parseProxyResponse(response.text);
  return {
    score,
    flagged,
    usage: response.usage,
  };
}
