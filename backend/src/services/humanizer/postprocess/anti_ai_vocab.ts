// backend/src/services/humanizer/postprocess/anti_ai_vocab.ts

// Deterministic post-process that strips the most-flagged "AI vocabulary"
// signals. Targets the GPTZero "AI Vocab" panel directly:
//   - Latinate verbs ("utilize", "facilitate", "leverage")
//   - Formal connectors at sentence/paragraph starts ("Furthermore",
//     "Moreover", "Additionally", "In conclusion")
//   - Cliché collocations ("pivotal role", "significant potential",
//     "ethical considerations")
//
// Used standalone (M17) and as a layer under M7 (M19). Pure string ops,
// ~1ms runtime, no LLM cost.

const SUBSTITUTIONS: Array<[RegExp, string]> = [
  // Latinate verbs → plain English. Capture leading word boundary, replace
  // with the same boundary so we don't accidentally hit "publication" etc.
  [/\butilize[ds]?\b/gi, 'use'],
  [/\bfacilitate[ds]?\b/gi, 'help'],
  [/\bleverage[ds]?\b/gi, 'use'],
  [/\bencompass(?:e[ds])?\b/gi, 'cover'],
  [/\bdemonstrate[ds]?\b/gi, 'show'],
  [/\bunderscore[ds]?\b/gi, 'highlight'],
  [/\bdelve[ds]? into\b/gi, 'look at'],
  [/\bnavigate[ds]? the\b/gi, 'work through the'],
  // Cliché AI collocations → unmark the specific bigram, leave words alone.
  [/\bpivotal role\b/gi, 'central role'],
  [/\bsignificant potential\b/gi, 'real promise'],
  [/\bethical considerations\b/gi, 'ethical questions'],
  [/\bcomprehensive feedback\b/gi, 'detailed feedback'],
  [/\bcutting[- ]edge\b/gi, 'recent'],
  [/\bgame[- ]chang(?:er|ing)\b/gi, 'major shift'],
  [/\bever[- ]evolving\b/gi, 'changing'],
  // Hedge fillers at sentence start.
  [/(^|[.!?]\s+)It is worth noting that\s+/g, '$1'],
  [/(^|[.!?]\s+)It is important to note that\s+/g, '$1'],
];

// Connectors that flag a sentence as AI when they appear AT THE START.
// We don't strip them mid-sentence — the issue is the metronomic
// "Furthermore, X. Moreover, Y. Additionally, Z." pattern.
const PARAGRAPH_START_CONNECTORS = [
  'Furthermore', 'Moreover', 'Additionally', 'In conclusion',
  'In summary', 'Notably', 'Importantly',
];

function stripParagraphStartConnectors(text: string): string {
  // For each connector, remove it (and the trailing comma+space) when it
  // appears immediately after a sentence boundary. Capitalize the next word.
  let out = text;
  for (const c of PARAGRAPH_START_CONNECTORS) {
    const pat = new RegExp(`(^|[.!?]\\s+)${c},\\s+([a-z])`, 'g');
    out = out.replace(pat, (_, pre, ch) => pre + ch.toUpperCase());
  }
  return out;
}

export function stripAiVocab(text: string): string {
  let out = text;
  for (const [pat, repl] of SUBSTITUTIONS) {
    out = out.replace(pat, repl);
  }
  out = stripParagraphStartConnectors(out);
  return out;
}
