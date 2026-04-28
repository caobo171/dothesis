// backend/src/services/humanizer/stylometric/scorer.ts

// Deterministic stylometric scorer used by M5 to rank candidate drafts.
// All four sub-features are normalized so each contributes ~equally to the
// final score. Lower score = more human-like (higher burstiness, higher
// vocabulary diversity, function-word ratio in human range, varied
// punctuation).

const HUMAN_FUNCTION_WORD_RATIO = 0.45; // empirical mid-range for English prose
const FUNCTION_WORDS = new Set([
  'the','a','an','and','or','but','if','then','of','in','on','at','to','for',
  'with','from','by','as','is','are','was','were','be','been','being','have',
  'has','had','do','does','did','will','would','could','should','can','may',
  'might','this','that','these','those','i','you','he','she','it','we','they',
  'me','him','her','us','them','my','your','his','its','our','their','not',
]);

function tokens(text: string): string[] {
  return (text.toLowerCase().match(/\b[a-z']+\b/g) || []);
}

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

export function sentenceLengthSigma(text: string): number {
  const lens = splitSentences(text).map(s => tokens(s).length);
  if (lens.length < 2) return 0;
  const mean = lens.reduce((a, b) => a + b, 0) / lens.length;
  const variance = lens.reduce((a, b) => a + (b - mean) ** 2, 0) / lens.length;
  return Math.sqrt(variance);
}

function typeTokenRatio(text: string): number {
  const t = tokens(text);
  if (t.length === 0) return 0;
  return new Set(t).size / t.length;
}

function functionWordRatio(text: string): number {
  const t = tokens(text);
  if (t.length === 0) return 0;
  const fw = t.filter(w => FUNCTION_WORDS.has(w)).length;
  return fw / t.length;
}

function punctuationEntropy(text: string): number {
  // Shannon entropy over the distribution of punctuation marks. Higher = more
  // varied punctuation rhythm; humans use a wider mix than AI.
  const puncts = (text.match(/[.,;:!?\-—()"]/g) || []);
  if (puncts.length === 0) return 0;
  const counts = new Map<string, number>();
  for (const p of puncts) counts.set(p, (counts.get(p) || 0) + 1);
  const total = puncts.length;
  let h = 0;
  for (const c of counts.values()) {
    const p = c / total;
    h -= p * Math.log2(p);
  }
  return h;
}

// Combined score: lower is more human-like.
// - burstiness: penalize σ < 7 (AI range), reward σ ∈ [7, 14]
// - typeTokenRatio: reward higher (more varied vocab)
// - functionWordRatio: penalize distance from HUMAN_FUNCTION_WORD_RATIO
// - punctuationEntropy: reward higher
export function stylometricScore(text: string): number {
  const sigma = sentenceLengthSigma(text);
  const ttr = typeTokenRatio(text);
  const fwr = functionWordRatio(text);
  const pe = punctuationEntropy(text);

  const burstinessPenalty = Math.max(0, 7 - sigma) * 5;        // 0 if σ ≥ 7, up to 35
  const ttrPenalty = Math.max(0, 0.5 - ttr) * 50;              // 0 if ttr ≥ 0.5
  const fwrPenalty = Math.abs(fwr - HUMAN_FUNCTION_WORD_RATIO) * 50;
  const punctPenalty = Math.max(0, 2.0 - pe) * 5;              // 0 if entropy ≥ 2 bits

  return burstinessPenalty + ttrPenalty + fwrPenalty + punctPenalty;
}
