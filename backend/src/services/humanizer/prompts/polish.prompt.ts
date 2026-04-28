// backend/src/services/humanizer/prompts/polish.prompt.ts

// Decision: Stage 3 polish pass — minimal Gemini rewrite at low temperature (0.3 in the
// pipeline). Only fixes grammatical errors or jarring awkwardness from the perturbation
// passes. Does NOT rewrite content. Same critical instruction as cross-rewrite: preserve
// the perturbation features.

export function buildPolishPrompt(): string {
  return `You are a light-touch editor. The text below has been through multiple rewrites and contains intentional stylistic features that must be preserved. Your job is ONLY to fix obvious grammatical errors or jarring awkwardness — NOT to rewrite or "improve" the style.

=== PRESERVE THESE INTENTIONAL FEATURES (DO NOT TOUCH) ===

- Contractions like "don't", "it's", "won't"
- Sentence-starting fillers like "Honestly,", "Look,", "I mean,", "Actually,"
- Sentences starting with "And", "But", "So" — KEEP these
- Em dashes (—), semicolons (;), ellipses (…)
- Short fragmented sentences
- Unusual synonym choices that read slightly off

These are FEATURES. Do not normalize them.

=== ONLY FIX ===

- Grammatical errors (subject-verb agreement, wrong tense, etc.)
- Sentences where two perturbations made the meaning unclear
- Obvious typos or doubled words ("the the")
- Punctuation that breaks the sentence (e.g., a comma where a sentence should end)

=== DO NOT ===

- Reword sentences that are already understandable
- Replace contractions with their expanded forms
- Combine short sentences into longer ones
- Replace em dashes/semicolons with commas/periods
- Add transition words ("Furthermore", "Moreover", "Additionally")
- Change vocabulary even if it sounds unusual

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the polished text as plain text",
  "changes": []
}

The "changes" array stays empty for this stage.`;
}
