// backend/src/services/humanizer/prompts/cross-rewrite.prompt.ts

// Decision: Stage 2 prompt for GPT. Critical instruction: PRESERVE the perturbations
// (contractions, fillers, sentence splits, em dashes, conjunction starters) introduced
// by the perturbation engine — otherwise GPT will "fix" them back into smooth LLM-style
// text and undo the breakthrough piece. Cross-model rewriting is meant to mix GPT's
// distribution over Gemini's perturbed output, not to clean it up.

export function buildCrossRewritePrompt(tone: string): string {
  const toneNote =
    tone === 'academic'
      ? 'Maintain an academic register — but with the personality of someone who actually cares about the topic.'
      : tone === 'casual'
        ? 'Maintain a casual, conversational register.'
        : 'Maintain a persuasive, opinionated register.';

  return `You are rewriting text that has already been humanized once and then deliberately perturbed for stylistic variety. Your job is to rewrite each sentence in your own voice WHILE PRESERVING the human-like irregularities the previous pass introduced.

${toneNote}

=== CRITICAL: PRESERVE THESE PERTURBATIONS ===

The input intentionally contains:
- Contractions ("don't", "it's", "won't") — KEEP them, do not expand to "do not", "it is"
- Sentence-starting fillers ("Honestly,", "Look,", "I mean,", "Actually,") — KEEP them
- Sentences starting with conjunctions ("And", "But", "So") — KEEP them, this is intentional
- Em dashes (—), semicolons, and ellipses (…) — KEEP them, do not replace with periods or commas
- Short fragmented sentences split from longer ones — KEEP them split
- Unusual synonym choices — KEEP them, do not "smooth" them back to common words

If you remove or smooth out these features, the output will fail AI detection. They are FEATURES, not bugs.

=== WHAT YOU SHOULD DO ===

1. Rewrite the underlying sentences in your own phrasing — change verb choices, restructure clauses, vary openings
2. Keep all facts, numbers, claims, and arguments intact
3. The output should READ as if you wrote it from scratch — but retain the perturbation features above
4. Aim for the same length (±15%) as the input

=== ANTI-PATTERNS TO AVOID ===

- Do NOT chain clauses with ", and it..." or ", but it..." (use semicolons or split sentences)
- Do NOT use formulaic transitions ("Furthermore", "Moreover", "Additionally", "In conclusion")
- Do NOT use these AI-flagged words: delve, leverage, utilize, foster, navigate, robust, innovative, seamless, cutting-edge, multifaceted, comprehensive, landscape, realm, tapestry, synergy, testament, myriad, paradigm shift
- Do NOT make the text uniformly hedged — be confident in 70% of statements

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": []
}

The "changes" array can be empty for this stage.`;
}
