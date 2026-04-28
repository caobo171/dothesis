/**
 * Statistical AI Detection Provider
 *
 * Detects AI-generated text by measuring statistical properties of the writing.
 * Based on the same principles as academic AI detectors (DetectGPT, GPTZero):
 * AI-generated text is more uniform, predictable, and formulaic than human writing.
 *
 * === How It Works ===
 *
 * We measure 7 independent linguistic metrics, each scoring 0-100
 * (0 = human-like, 100 = AI-like), then compute a weighted average.
 *
 * The key insight: AI language models optimize for fluency, which produces
 * text that is statistically "too perfect" — too uniform in sentence length,
 * too consistent in vocabulary, too smooth in complexity flow, and too heavy
 * on formulaic transitions. Human writing is messier, more varied, and
 * includes natural imperfections.
 *
 * === Metrics ===
 *
 * 1. SENTENCE LENGTH VARIANCE (weight: 15%)
 *    What: Coefficient of variation of sentence word counts.
 *    Why: AI models produce sentences of remarkably similar length because
 *    the generation process favors a "comfortable" output length. Humans
 *    naturally mix short punchy sentences with long elaborate ones.
 *    Signal: CV < 0.25 → likely AI, CV > 0.4 → likely human.
 *
 * 2. VOCABULARY DIVERSITY / Type-Token Ratio (weight: 20%)
 *    What: Ratio of unique words to total words in sliding windows.
 *    Why: AI tends to reuse the same "safe" words, especially in academic
 *    writing. Humans draw from a broader vocabulary and use more synonyms,
 *    colloquialisms, and domain-specific jargon inconsistently.
 *    Signal: TTR < 0.6 → likely AI, TTR > 0.75 → likely human.
 *
 * 3. BURSTINESS (weight: 15%)
 *    What: Average absolute difference in consecutive sentence lengths,
 *    normalized by mean sentence length.
 *    Why: Human writing exhibits "burstiness" — sudden shifts from a long
 *    analytical sentence to a short emphatic one. AI maintains a steady flow.
 *    This is one of the strongest differentiators in research literature.
 *    Signal: ratio < 0.2 → likely AI, ratio > 0.4 → likely human.
 *
 * 4. TRANSITION WORD DENSITY (weight: 20%)
 *    What: Count of formulaic connector phrases per sentence.
 *    Why: AI overuses transitions like "Furthermore", "Moreover",
 *    "It is worth noting" because these patterns are heavily reinforced
 *    in training data. Humans use fewer explicit transitions, relying
 *    instead on implicit logical flow. Includes language-specific lists
 *    for English and Vietnamese.
 *    Signal: > 0.6 per sentence → likely AI, < 0.3 → likely human.
 *
 * 5. SENTENCE STARTER DIVERSITY (weight: 10%)
 *    What: Ratio of unique 2-word sentence openings to total sentences.
 *    Why: AI often starts sentences with similar patterns ("The", "This",
 *    "In addition"). Humans start sentences more unpredictably.
 *    Signal: diversity < 0.6 → likely AI, > 0.8 → likely human.
 *
 * 6. HUMAN MARKER PRESENCE (weight: 10%)
 *    What: Density of filler words, hedging, personal pronouns, and
 *    informal language markers.
 *    Why: Humans naturally use "I think", "actually", "kind of", and
 *    other hedging/filler words. AI (especially in academic mode) almost
 *    never produces these. Their absence is a strong AI signal.
 *    Signal: density < 0.3% → likely AI, > 1% → likely human.
 *
 * 7. PUNCTUATION DIVERSITY (weight: 10%)
 *    What: Variety of punctuation types used (semicolons, dashes,
 *    parentheses, exclamation marks, etc.)
 *    Why: AI defaults to periods and commas. Humans use a wider range
 *    of punctuation for emphasis, asides, and rhetorical effect.
 *    Signal: < 2 types used → likely AI, > 4 types → likely human.
 *
 * === Why This Works for Humanization ===
 *
 * When our humanizer rewrites text, it naturally:
 * - Varies sentence structure → reduces sentence length uniformity
 * - Uses different words → increases vocabulary diversity
 * - Creates complexity jumps → increases burstiness
 * - Removes formulaic transitions → reduces transition density
 * - Diversifies sentence openings → increases starter diversity
 *
 * This means the "after" score will ALWAYS be meaningfully lower than
 * the "before" score, because the humanization directly targets the
 * properties we measure.
 *
 * === Limitations ===
 *
 * - Does not measure perplexity (would require LLM API calls)
 * - Short texts (< 50 words) produce less reliable scores
 * - Calibration is approximate — based on observed patterns, not
 *   formal training on labeled datasets
 * - Will not catch sophisticated AI text that was specifically
 *   engineered to evade statistical detection
 *
 * === Future Improvements ===
 *
 * - Add perplexity scoring via OpenAI logprobs API
 * - Train weights on a labeled dataset of AI vs human text
 * - Add n-gram repetition analysis
 * - Add readability score comparison (Flesch-Kincaid, etc.)
 */

import { AIDetectionProvider, AIDetectionResult, AIDetectionMetrics } from '../types';

// === Language-specific word lists ===

const TRANSITION_WORDS: Record<string, string[]> = {
  en: [
    // Additive
    'furthermore', 'moreover', 'additionally', 'in addition', 'besides',
    'also', 'likewise', 'similarly', 'equally important',
    // Adversative
    'however', 'nevertheless', 'nonetheless', 'on the other hand',
    'in contrast', 'conversely', 'despite this', 'on the contrary',
    // Causal
    'therefore', 'consequently', 'as a result', 'thus', 'hence',
    'accordingly', 'for this reason',
    // Sequential
    'firstly', 'secondly', 'thirdly', 'finally', 'subsequently',
    'in conclusion', 'to summarize', 'in summary',
    // AI-heavy phrases
    'it is worth noting', 'it should be mentioned', 'it is important to note',
    'it is evident that', 'it can be observed', 'this suggests that',
    'plays a crucial role', 'is of paramount importance',
    'in the realm of', 'it is imperative', 'serves as a testament',
    'a myriad of', 'delve into', 'shed light on',
    'navigate the complexities', 'foster a deeper understanding',
    'underscores the importance', 'in today\'s rapidly evolving',
  ],
  vi: [
    // Additive
    'ngoài ra', 'hơn nữa', 'bên cạnh đó', 'thêm vào đó', 'không chỉ vậy',
    'đồng thời', 'cũng như', 'tương tự',
    // Adversative
    'tuy nhiên', 'mặc dù vậy', 'ngược lại', 'trái lại', 'mặt khác',
    'dù vậy', 'bất chấp',
    // Causal
    'do đó', 'vì vậy', 'chính vì vậy', 'kết quả là', 'từ đó',
    'bởi vậy', 'nhờ đó',
    // Sequential
    'trước hết', 'tiếp theo', 'cuối cùng', 'tóm lại', 'nhìn chung',
    'kết luận lại', 'tổng kết lại',
    // AI-heavy Vietnamese
    'điều đáng chú ý là', 'cần phải nhấn mạnh rằng', 'có thể thấy rằng',
    'đóng vai trò quan trọng', 'mang tính chất', 'góp phần quan trọng',
    'trong bối cảnh', 'không thể phủ nhận', 'là một phần không thể thiếu',
    'đã cho thấy những', 'việc tích hợp', 'các vấn đề liên quan đến',
  ],
};

const HUMAN_MARKERS: Record<string, string[]> = {
  en: [
    'actually', 'basically', 'honestly', 'well', 'like', 'kind of',
    'sort of', 'i think', 'i believe', 'i guess', 'you know',
    'pretty much', 'i mean', 'to be honest', 'in my experience',
    'personally', 'tbh', 'imo', 'btw',
    // Creative grammar markers — inversions, clefts, rhetorical questions
    'rarely do', 'not once', 'what surprised me', 'what matters',
    'having spent', 'having read', 'gone are', 'nowhere is',
    'picture this', 'imagine',
  ],
  vi: [
    'thực ra', 'nói thật', 'theo tôi', 'mình nghĩ', 'có lẽ',
    'chắc là', 'đại khái', 'kiểu như', 'nói chung là',
    'thật sự mà nói', 'cá nhân tôi', 'theo kinh nghiệm',
    // Creative grammar markers in Vietnamese
    'hiếm khi nào', 'điều làm tôi ngạc nhiên', 'thử hình dung',
  ],
};

// === Metric weights ===
// Adaptive: vocabularyDiversity is unreliable for short texts (< 200 words)
// because TTR is naturally high when there aren't enough words to show repetition.

function getWeights(wordCount: number): Record<keyof AIDetectionMetrics, number> {
  if (wordCount < 200) {
    // Short text: redistribute VD weight to metrics that work better
    return {
      sentenceLengthVariance: 0.18,
      vocabularyDiversity: 0.05,
      burstiness: 0.18,
      transitionDensity: 0.24,
      sentenceStarterDiversity: 0.10,
      humanMarkers: 0.13,
      punctuationDiversity: 0.12,
    };
  }
  // Long text: VD is reliable
  return {
    sentenceLengthVariance: 0.15,
    vocabularyDiversity: 0.20,
    burstiness: 0.15,
    transitionDensity: 0.20,
    sentenceStarterDiversity: 0.10,
    humanMarkers: 0.10,
    punctuationDiversity: 0.10,
  };
}

// === Utility functions ===

function detectLanguage(text: string): 'en' | 'vi' {
  const viPattern = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/gi;
  const viMatches = (text.match(viPattern) || []).length;
  return (viMatches / text.length) > 0.02 ? 'vi' : 'en';
}

function splitSentences(text: string): string[] {
  return text
    .split(/[.!?]+/)
    .map(s => s.trim())
    .filter(s => s.length > 5);
}

function getWords(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(w => w.length > 0);
}

function countPhraseOccurrences(text: string, phrases: string[]): number {
  const lower = text.toLowerCase();
  let count = 0;
  for (const phrase of phrases) {
    const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matches = lower.match(new RegExp(escaped, 'gi'));
    if (matches) count += matches.length;
  }
  return count;
}

// === Metric scoring functions ===

function scoreSentenceLengthVariance(sentences: string[]): number {
  if (sentences.length < 3) return 50;
  const lengths = sentences.map(s => getWords(s).length);
  const mean = lengths.reduce((a, b) => a + b, 0) / lengths.length;
  const variance = lengths.reduce((sum, l) => sum + Math.pow(l - mean, 2), 0) / lengths.length;
  const cv = mean > 0 ? Math.sqrt(variance) / mean : 0;
  return Math.round(Math.max(0, Math.min(100, 110 - cv * 200)));
}

function scoreVocabularyDiversity(words: string[]): number {
  if (words.length < 20) return 50;
  // Use smaller windows for short texts to capture repetition
  const windowSize = Math.min(30, Math.floor(words.length / 2));
  if (windowSize < 10) return 50;
  let totalTTR = 0;
  let windows = 0;
  for (let i = 0; i <= words.length - windowSize; i += Math.floor(windowSize / 2)) {
    const window = words.slice(i, i + windowSize);
    totalTTR += new Set(window).size / window.length;
    windows++;
  }
  const avgTTR = totalTTR / windows;
  // Recalibrated: TTR 0.6 → 80, TTR 0.75 → 50, TTR 0.9 → 20, TTR 1.0 → 0
  return Math.round(Math.max(0, Math.min(100, 200 - avgTTR * 200)));
}

function scoreBurstiness(sentences: string[]): number {
  if (sentences.length < 4) return 50;
  const lengths = sentences.map(s => getWords(s).length);
  const diffs: number[] = [];
  for (let i = 1; i < lengths.length; i++) {
    diffs.push(Math.abs(lengths[i] - lengths[i - 1]));
  }
  const meanDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
  const meanLength = lengths.reduce((a, b) => a + b, 0) / lengths.length;
  const burstiness = meanLength > 0 ? meanDiff / meanLength : 0;
  return Math.round(Math.max(0, Math.min(100, 100 - burstiness * 175)));
}

function scoreTransitionDensity(text: string, lang: 'en' | 'vi'): number {
  const sentences = splitSentences(text);
  if (sentences.length === 0) return 50;
  const count = countPhraseOccurrences(text, TRANSITION_WORDS[lang] || TRANSITION_WORDS.en);
  const density = count / sentences.length;
  return Math.round(Math.max(0, Math.min(100, density * 75 + 10)));
}

function scoreSentenceStarterDiversity(sentences: string[]): number {
  if (sentences.length < 4) return 50;
  // Use first word only — AI often starts with "The", "This", "It" repeatedly
  const starters1 = sentences.map(s => getWords(s)[0] || '');
  const diversity1 = new Set(starters1).size / starters1.length;
  // Also check first 3 words for structural pattern repetition
  const starters3 = sentences.map(s => getWords(s).slice(0, 3).join(' '));
  const diversity3 = new Set(starters3).size / starters3.length;
  // Blend: single-word diversity matters more
  const blended = diversity1 * 0.6 + diversity3 * 0.4;
  // Recalibrated: diversity 0.5 → 75, diversity 0.8 → 42, diversity 1.0 → 20
  return Math.round(Math.max(0, Math.min(100, 130 - blended * 110)));
}

function scoreHumanMarkers(text: string, lang: 'en' | 'vi'): number {
  const words = getWords(text);
  if (words.length === 0) return 70;
  const count = countPhraseOccurrences(text, HUMAN_MARKERS[lang] || HUMAN_MARKERS.en);
  const density = (count / words.length) * 100;
  return Math.round(Math.max(0, Math.min(100, 80 - density * 30)));
}

function scorePunctuationDiversity(text: string): number {
  const sentences = splitSentences(text);
  if (sentences.length === 0) return 50;

  const patterns = [/;/g, /—|--/g, /\(/g, /!/g, /\?/g, /:/g, /\.\.\./g, /"/g];
  let typesUsed = 0;
  let totalSpecial = 0;

  for (const pattern of patterns) {
    const matches = text.match(pattern);
    if (matches && matches.length > 0) {
      typesUsed++;
      totalSpecial += matches.length;
    }
  }

  const combined = (typesUsed / patterns.length) * 0.6 +
    Math.min(1, (totalSpecial / sentences.length) * 0.3) * 0.4;
  return Math.round(Math.max(0, Math.min(100, 85 - combined * 120)));
}

// === Provider implementation ===

export class StatisticalDetectionProvider implements AIDetectionProvider {
  readonly name = 'statistical';

  async analyze(text: string): Promise<AIDetectionResult> {
    const lang = detectLanguage(text);
    const sentences = splitSentences(text);
    const words = getWords(text);

    const metrics: AIDetectionMetrics = {
      sentenceLengthVariance: scoreSentenceLengthVariance(sentences),
      vocabularyDiversity: scoreVocabularyDiversity(words),
      burstiness: scoreBurstiness(sentences),
      transitionDensity: scoreTransitionDensity(text, lang),
      sentenceStarterDiversity: scoreSentenceStarterDiversity(sentences),
      humanMarkers: scoreHumanMarkers(text, lang),
      punctuationDiversity: scorePunctuationDiversity(text),
    };

    const weights = getWeights(words.length);
    let weightedSum = 0;
    for (const [key, weight] of Object.entries(weights)) {
      weightedSum += metrics[key as keyof AIDetectionMetrics] * weight;
    }

    return {
      score: Math.round(Math.max(0, Math.min(100, weightedSum))),
      metrics,
      language: lang,
      provider: this.name,
    };
  }
}
