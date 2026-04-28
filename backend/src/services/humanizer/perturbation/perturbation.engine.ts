// backend/src/services/humanizer/perturbation/perturbation.engine.ts

// Decision: PerturbationEngine is a static class with a single public method `perturb`.
// It splits text into sentences, decides per-sentence whether to perturb based on rate,
// picks 1-2 random operations per perturbed sentence, applies them, and reassembles.
// The rng parameter defaults to Math.random but can be overridden for deterministic tests.

import { ALL_OPERATIONS, Lang, RNG } from './operations';

// Reuse language detection from statistical detector — keeps both modules in sync.
function detectLanguage(text: string): Lang {
  const viPattern = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/gi;
  const viMatches = (text.match(viPattern) || []).length;
  return (viMatches / text.length) > 0.02 ? 'vi' : 'en';
}

// Sentence splitter — keeps the sentence-ending punctuation attached.
// Uses lookbehind to split on .!? followed by whitespace.
function splitIntoSentences(text: string): string[] {
  // Split keeping the punctuation. Match: word/non-punct chars then .!? then whitespace.
  const matches = text.match(/[^.!?]+[.!?]+(?:\s+|$)/g);
  if (!matches) return [text];
  return matches.map(s => s.trim()).filter(s => s.length > 0);
}

export class PerturbationEngine {
  // Decision: Rate scales with strength so users get more aggressive perturbation
  // when they ask for stronger humanization. The numbers (0.20, 0.35, 0.50) were
  // chosen so that even the lightest setting still produces visible non-LLM signal,
  // while the strongest setting stops short of making text obviously broken.
  static getRate(strength: number): number {
    if (strength <= 30) return 0.20;
    if (strength <= 70) return 0.35;
    return 0.50;
  }

  static perturb(text: string, strength: number, rng: RNG = Math.random): string {
    const lang = detectLanguage(text);
    const rate = this.getRate(strength);
    const sentences = splitIntoSentences(text);

    const result: string[] = [];

    for (const sentence of sentences) {
      // Decide whether to perturb this sentence
      if (rng() > rate) {
        result.push(sentence);
        continue;
      }

      // Pick 1 or 2 operations randomly (50/50 chance for 2 ops)
      const opCount = rng() < 0.5 ? 1 : 2;
      const chosenOps = this.pickRandomOps(opCount, rng);

      let perturbed = sentence;
      for (const op of chosenOps) {
        perturbed = op(perturbed, lang, rng);
      }
      result.push(perturbed);
    }

    return result.join(' ');
  }

  private static pickRandomOps(count: number, rng: RNG) {
    // Shuffle a copy of ALL_OPERATIONS and take the first `count`
    const shuffled = [...ALL_OPERATIONS];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled.slice(0, count);
  }
}
