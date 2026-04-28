// backend/src/services/humanizer/perturbation/operations.ts

// Decision: Each operation is a pure function — given the same sentence, lang, and rng
// output, it produces the same output. This makes the engine deterministic for testing
// when given a seeded RNG, while still random in production with Math.random.

import { SYNONYMS_EN, SYNONYMS_VI, SynonymMap } from './synonym.dictionary';
import {
  SENTENCE_STARTERS_EN,
  SENTENCE_STARTERS_VI,
  CONJUNCTION_STARTERS_EN,
  CONJUNCTION_STARTERS_VI,
  CONTRACTIONS_EN,
} from './human-markers';

export type Lang = 'en' | 'vi';
export type RNG = () => number;
export type PerturbationOp = (sentence: string, lang: Lang, rng: RNG) => string;

// Fix (Issue 4): throw on empty array so callers get a clear error instead of returning
// undefined silently and crashing downstream.
function pick<T>(arr: T[], rng: RNG): T {
  if (arr.length === 0) throw new Error('pick() called on empty array');
  return arr[Math.floor(rng() * arr.length)];
}

// Op 1: Synonym swap — pick one matching word in the sentence and replace with a synonym
export const synonymSwap: PerturbationOp = (sentence, lang, rng) => {
  const dict: SynonymMap = lang === 'vi' ? SYNONYMS_VI : SYNONYMS_EN;
  const lower = sentence.toLowerCase();
  const candidates: Array<{ word: string; alternatives: string[] }> = [];

  for (const word of Object.keys(dict)) {
    if (!lower.includes(word)) continue;
    // Fix (Issue 5): pre-filter with the real regex to avoid false-positive candidates
    // (e.g. 'significant' matching 'insignificant') that would consume an RNG call when
    // picked but then fail to replace anything, breaking test determinism.
    // Fix (Bug 2): \b is ASCII-based and fails for Vietnamese keys ending/starting in
    // diacritics. For VI we drop the boundary anchor (false-positive risk is low because
    // Vietnamese syllables are space-delimited).
    const testRegex = lang === 'vi'
      ? new RegExp(word, 'i')
      : new RegExp(`\\b${word}\\b`, 'i');
    if (testRegex.test(sentence)) {
      candidates.push({ word, alternatives: dict[word] });
    }
  }

  if (candidates.length === 0) return sentence;
  const chosen = pick(candidates, rng);
  const replacement = pick(chosen.alternatives, rng);

  // Case-insensitive replace, preserve original casing of first letter if it was capitalized.
  // Decision: \b is ASCII-based and fails for Vietnamese keys ending/starting in
  // diacritics. For VI we drop the boundary anchor (false-positive risk is low
  // because Vietnamese syllables are space-delimited).
  const regex = lang === 'vi'
    ? new RegExp(chosen.word, 'i')
    : new RegExp(`\\b${chosen.word}\\b`, 'i');
  return sentence.replace(regex, (match) => {
    if (match[0] === match[0].toUpperCase()) {
      return replacement[0].toUpperCase() + replacement.slice(1);
    }
    return replacement;
  });
};

// Op 2: Contraction toggle — find a contractable phrase and contract it (EN only)
export const toggleContraction: PerturbationOp = (sentence, lang, rng) => {
  if (lang !== 'en') return sentence;
  const lower = sentence.toLowerCase();
  const candidates: Array<{ phrase: string; contracted: string }> = [];

  for (const [phrase, contracted] of Object.entries(CONTRACTIONS_EN)) {
    // Fix (Bug 3): dictionary keys include uppercase 'I' (e.g. 'I am', 'I have') but
    // lower is fully lowercased, so we must also lowercase the phrase before comparing.
    if (lower.includes(phrase.toLowerCase())) {
      candidates.push({ phrase, contracted });
    }
  }

  if (candidates.length === 0) return sentence;
  const chosen = pick(candidates, rng);
  // Fix (Bug 3): use lowercased phrase in the regex so it aligns with what we matched
  // above. The 'i' flag handles the actual case-insensitive replacement.
  const regex = new RegExp(`\\b${chosen.phrase.toLowerCase()}\\b`, 'i');
  return sentence.replace(regex, (match) => {
    if (match[0] === match[0].toUpperCase()) {
      return chosen.contracted[0].toUpperCase() + chosen.contracted.slice(1);
    }
    return chosen.contracted;
  });
};

// Op 3: Human marker injection — prepend a filler phrase to the sentence
export const injectHumanMarker: PerturbationOp = (sentence, lang, rng) => {
  // Fix (Bug 1): guard against empty sentence to avoid crash on sentence[0].toLowerCase()
  if (!sentence) return sentence;
  const markers = lang === 'vi' ? SENTENCE_STARTERS_VI : SENTENCE_STARTERS_EN;
  const marker = pick(markers, rng);
  // Lowercase the first letter of the original sentence since the marker ends with a comma+space
  const adjusted = sentence[0].toLowerCase() + sentence.slice(1);
  return marker + adjusted;
};

// Op 4: Sentence splitting — split on a comma into two sentences
export const splitSentence: PerturbationOp = (sentence, _lang, rng) => {
  // Find comma positions that are at least 4 words from start and 4 words from end
  const commaIndices: number[] = [];
  for (let i = 0; i < sentence.length; i++) {
    if (sentence[i] === ',') commaIndices.push(i);
  }
  if (commaIndices.length === 0) return sentence;

  // Pick a random comma to split on
  const splitIdx = pick(commaIndices, rng);
  const before = sentence.slice(0, splitIdx).trim();
  const after = sentence.slice(splitIdx + 1).trim();

  // Fix (Bug 1): guard against empty halves before accessing [0] — place before the
  // word-count check so we never crash on after[0].toUpperCase() below.
  if (!before || !after) return sentence;

  // Only split if both halves are at least 3 words
  if (before.split(/\s+/).length < 3 || after.split(/\s+/).length < 3) return sentence;

  // Capitalize the start of the second half
  const afterCapitalized = after[0].toUpperCase() + after.slice(1);
  return `${before}. ${afterCapitalized}`;
};

// Op 5: Punctuation variation — replace one period at the end of an internal clause with
// a semicolon or em dash, OR add an em dash for an aside.
export const varyPunctuation: PerturbationOp = (sentence, _lang, rng) => {
  // Find a comma to upgrade to em dash (more dramatic)
  const commaIndices: number[] = [];
  // Fix (Issue 6): exclude the last character position — a trailing comma replaced with
  // an em dash or semicolon is ungrammatical.
  for (let i = 0; i < sentence.length - 1; i++) {
    // Skip trailing commas — replacing them with em dashes/semicolons is ungrammatical
    if (sentence[i] === ',') commaIndices.push(i);
  }
  if (commaIndices.length === 0) return sentence;

  const targetComma = pick(commaIndices, rng);
  const choice = rng();
  let replacement: string;
  if (choice < 0.5) replacement = ' —';
  else if (choice < 0.8) replacement = ';';
  else replacement = ' …';

  return sentence.slice(0, targetComma) + replacement + sentence.slice(targetComma + 1);
};

// Op 6: Starter variation — prepend a conjunction starter (And, But, So, etc.)
export const varyStarter: PerturbationOp = (sentence, lang, rng) => {
  // Fix (Bug 1): guard against empty sentence to avoid crash on sentence[0].toLowerCase()
  if (!sentence) return sentence;
  const starters = lang === 'vi' ? CONJUNCTION_STARTERS_VI : CONJUNCTION_STARTERS_EN;
  const starter = pick(starters, rng);
  const adjusted = sentence[0].toLowerCase() + sentence.slice(1);
  return starter + adjusted;
};

export const ALL_OPERATIONS: PerturbationOp[] = [
  synonymSwap,
  toggleContraction,
  injectHumanMarker,
  splitSentence,
  varyPunctuation,
  varyStarter,
];
