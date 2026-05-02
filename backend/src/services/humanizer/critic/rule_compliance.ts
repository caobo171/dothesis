// backend/src/services/humanizer/critic/rule_compliance.ts

// Decision: Pure-function checker — no LLM, no IO. The four rules are all
// mechanically measurable text features; using regex/heuristics keeps the
// critic free, fast, and deterministic. This is the key insight that makes
// M23 viable where M1/M2/M9 (LLM critics) failed: a checker that grades
// "did you apply rule X?" can give quantitative feedback to the regeneration
// call, while LLM critics that grade "is this still AI?" historically gave
// noise that didn't correlate with detector outputs.
//
// Spec: docs/superpowers/specs/2026-05-02-humanizer-m23-rules-critic-design.md

export type RuleId = 'hedging' | 'fronted_openings' | 'no_expansion' | 'anti_x_and_y';

export type RuleViolation = {
  rule: RuleId;
  measured: number;
  threshold: number;
  feedbackForLLM: string;
};

export type ComplianceMetrics = {
  inputWords: number;
  outputWords: number;
  hedgeCount: number;
  hedgeRatePer100Words: number;
  sentenceCount: number;
  frontedClauseCount: number;
  frontedClauseRatio: number;
  xAndYCount: number;
  xAndYRatePer100Words: number;
  expansionRatio: number;
};

export type ComplianceReport = {
  passed: boolean;
  violations: RuleViolation[];
  metrics: ComplianceMetrics;
};

// Hedge tokens — multi-word patterns and single words. Multi-word patterns
// must come first since they're more specific.
const HEDGE_PATTERNS: RegExp[] = [
  /\bis\s+believed\b/gi,
  /\bis\s+suspected\b/gi,
  /\bis\s+likely\b/gi,
  /\btends\s+to\b/gi,
  /\bappears\b/gi,
  /\bseems\b/gi,
  /\bmay\b/gi,
  /\bmight\b/gi,
  /\bcan\b/gi,
  /\bsuggests?\b/gi,
  /\barguably\b/gi,
  /\bpresumably\b/gi,
];

// Fronted-clause sentence openers. A sentence "starts with a fronted clause"
// when its first token is a subordinator, present participle, or fronted PP.
// Capitalized to match sentence-initial position.
const FRONTED_OPENERS = new Set([
  // Subordinators
  'although', 'though', 'while', 'whereas',
  'since', 'because', 'as',
  'despite', 'notwithstanding',
  'given', 'considering',
  'when', 'whenever', 'before', 'after', 'until', 'unless', 'if',
  // Present participles often start fronted clauses
  'looking', 'consider', 'considering', 'recognizing', 'noting',
  // Common fronted PP heads
  'in', 'across', 'under', 'within', 'beyond', 'throughout', 'amid', 'among',
  'by', 'through', 'with', 'without', 'against', 'during', 'beneath',
  // Adverbial fronts that count as "not subject-first"
  'historically', 'traditionally', 'increasingly', 'crucially', 'notably',
  'importantly', 'remarkably', 'arguably',
]);

// X-and-Y idiom whitelist — these "X and Y" patterns are fixed expressions,
// not parallel two-item lists, so they should NOT count as violations.
const X_AND_Y_IDIOM_WHITELIST = new Set([
  'back and forth',
  'more and more',
  'over and over',
  'up and down',
  'in and out',
  'now and then',
  'time and again',
  'on and on',
  'round and round',
  'side by side', // Not "X and Y" but listed for safety; won't match the regex anyway
  'give and take',
  'trial and error',
  'black and white',
  'rock and roll',
  'pros and cons',
]);

// Word-count helper: split on whitespace, filter empties.
function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// Sentence splitter — naive but adequate for English prose. Splits on
// .!? followed by whitespace. Filters empty fragments.
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// First word of a sentence, lowercased, stripped of leading punctuation.
function firstWord(sentence: string): string {
  const m = sentence.replace(/^[^\p{L}]+/u, '').match(/^(\S+)/);
  return m ? m[1].toLowerCase().replace(/[^\p{L}]+$/u, '') : '';
}

function countHedges(text: string): number {
  let total = 0;
  for (const re of HEDGE_PATTERNS) {
    const matches = text.match(re);
    if (matches) total += matches.length;
  }
  return total;
}

function countFrontedClauses(sentences: string[]): number {
  let count = 0;
  for (const s of sentences) {
    const w = firstWord(s);
    if (FRONTED_OPENERS.has(w)) count++;
  }
  return count;
}

// Two-item "X and Y" parallel lists. Match adjacent word + "and" + word
// where both are alphabetic (not numbers, not "and" itself).
function countXAndY(text: string): number {
  const re = /\b([A-Za-z]{2,})\s+and\s+([A-Za-z]{2,})\b/g;
  let count = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const phrase = `${m[1].toLowerCase()} and ${m[2].toLowerCase()}`;
    if (!X_AND_Y_IDIOM_WHITELIST.has(phrase)) count++;
  }
  return count;
}

// Thresholds — first-cut values from the design spec. Tuning these is part
// of the M23 bench iteration; record any threshold change in the v12 handoff.
const THRESHOLDS = {
  hedgeRatePer100Words: 2,        // ≥ 2 per 100 words
  frontedClauseRatio: 0.25,       // ≥ 25% of sentences
  expansionRatio: 1.05,           // ≤ 1.05 (output may exceed input by 5% max)
  xAndYRatePer100Words: 3,        // ≤ 3 per 100 words
};

export function checkRuleCompliance(input: string, output: string): ComplianceReport {
  const inputWords = countWords(input);
  const outputWords = countWords(output);
  const sentences = splitSentences(output);
  const sentenceCount = sentences.length;

  const hedgeCount = countHedges(output);
  const frontedClauseCount = countFrontedClauses(sentences);
  const xAndYCount = countXAndY(output);

  // Per-100-word rates. Guard against division by zero on empty output.
  const per100 = outputWords > 0 ? 100 / outputWords : 0;
  const hedgeRatePer100Words = hedgeCount * per100;
  const xAndYRatePer100Words = xAndYCount * per100;
  const frontedClauseRatio = sentenceCount > 0 ? frontedClauseCount / sentenceCount : 0;
  const expansionRatio = inputWords > 0 ? outputWords / inputWords : 0;

  const violations: RuleViolation[] = [];

  if (hedgeRatePer100Words < THRESHOLDS.hedgeRatePer100Words) {
    violations.push({
      rule: 'hedging',
      measured: hedgeRatePer100Words,
      threshold: THRESHOLDS.hedgeRatePer100Words,
      feedbackForLLM: `Hedging language: only ${hedgeCount} hedge tokens in ${outputWords} words (${hedgeRatePer100Words.toFixed(1)}/100w). Target ≥ ${THRESHOLDS.hedgeRatePer100Words}/100w. Use words like "appears", "seems", "may", "might", "can", "suggests", "is believed", "tends to" to soften factual statements where appropriate.`,
    });
  }

  if (frontedClauseRatio < THRESHOLDS.frontedClauseRatio) {
    violations.push({
      rule: 'fronted_openings',
      measured: frontedClauseRatio,
      threshold: THRESHOLDS.frontedClauseRatio,
      feedbackForLLM: `Fronted-clause sentence openings: only ${frontedClauseCount} of ${sentenceCount} sentences (${(frontedClauseRatio * 100).toFixed(0)}%) start with something other than the subject. Target ≥ ${(THRESHOLDS.frontedClauseRatio * 100).toFixed(0)}%. Start more sentences with "Although", "While", "Given", "Despite", "When", or with fronted prepositional phrases like "In recent years,", "Across the field,", "By contrast,".`,
    });
  }

  if (expansionRatio > THRESHOLDS.expansionRatio) {
    violations.push({
      rule: 'no_expansion',
      measured: expansionRatio,
      threshold: THRESHOLDS.expansionRatio,
      feedbackForLLM: `Output is too long: ${outputWords} words vs ${inputWords} input words (${expansionRatio.toFixed(2)}× expansion). Target ≤ ${THRESHOLDS.expansionRatio.toFixed(2)}×. Cut filler — vague generalizations, repeated points, and surface-level qualifiers — to bring length back in line.`,
    });
  }

  if (xAndYRatePer100Words > THRESHOLDS.xAndYRatePer100Words) {
    violations.push({
      rule: 'anti_x_and_y',
      measured: xAndYRatePer100Words,
      threshold: THRESHOLDS.xAndYRatePer100Words,
      feedbackForLLM: `Two-item "X and Y" lists: ${xAndYCount} occurrences in ${outputWords} words (${xAndYRatePer100Words.toFixed(1)}/100w). Target ≤ ${THRESHOLDS.xAndYRatePer100Words}/100w. Replace pairs like "social and educational" or "anxiety and fear" with single nouns, longer enumerations (three+ items), or rephrase to avoid the parallel pair.`,
    });
  }

  return {
    passed: violations.length === 0,
    violations,
    metrics: {
      inputWords,
      outputWords,
      hedgeCount,
      hedgeRatePer100Words,
      sentenceCount,
      frontedClauseCount,
      frontedClauseRatio,
      xAndYCount,
      xAndYRatePer100Words,
      expansionRatio,
    },
  };
}

export function formatRevisionFeedback(report: ComplianceReport): string {
  if (report.passed) return '';
  const lines = report.violations.map((v) => `- ${v.feedbackForLLM}`);
  return `Your previous rewrite missed these targets:\n${lines.join('\n')}\nApply these fixes while preserving the original meaning.`;
}
