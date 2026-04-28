// backend/src/services/humanizer/perturbation/human-markers.ts

// Decision: Sentence-start fillers that humans use in writing but LLMs almost never
// produce naturally in academic/formal text. Injecting these at the start of a small
// percentage of sentences mimics natural human prose rhythm.

export const SENTENCE_STARTERS_EN: string[] = [
  'Honestly, ',
  'Look, ',
  'I mean, ',
  'Actually, ',
  'Frankly, ',
  'Truthfully, ',
  'In reality, ',
  'To be fair, ',
  'Granted, ',
  'Sure, ',
];

export const SENTENCE_STARTERS_VI: string[] = [
  'Thực ra, ',
  'Nói thật, ',
  'Thẳng thắn mà nói, ',
  'Theo mình, ',
  'Nhìn chung, ',
  'Có điều, ',
  'Thật ra, ',
  'Phải công nhận, ',
];

// Decision: Conjunction starters (And, But, So) at the start of sentences are
// considered ungrammatical in academic writing — which is why LLMs avoid them.
// Humans do this constantly. Each is a strong signal of human authorship.
export const CONJUNCTION_STARTERS_EN: string[] = [
  'And ',
  'But ',
  'So ',
  'Still, ',
  'Yet ',
  'Plus, ',
];

export const CONJUNCTION_STARTERS_VI: string[] = [
  'Mà ',
  'Nhưng ',
  'Còn ',
  'Vậy nên ',
  'Thế nhưng ',
];

// Decision: Common English contractions. Maps non-contracted form → contracted form.
// LLMs are inconsistent about contractions in formal text — toggling some toward
// contractions and others away matches the natural human inconsistency.
export const CONTRACTIONS_EN: Record<string, string> = {
  'it is': "it's",
  'it has': "it's",
  'do not': "don't",
  'does not': "doesn't",
  'did not': "didn't",
  'is not': "isn't",
  'are not': "aren't",
  'was not': "wasn't",
  'were not': "weren't",
  'will not': "won't",
  'would not': "wouldn't",
  'could not': "couldn't",
  'should not': "shouldn't",
  'cannot': "can't",
  'can not': "can't",
  'have not': "haven't",
  'has not': "hasn't",
  'had not': "hadn't",
  'they are': "they're",
  'they have': "they've",
  'we are': "we're",
  'we have': "we've",
  'you are': "you're",
  'you have': "you've",
  'I am': "I'm",
  'I have': "I've",
  'that is': "that's",
  'there is': "there's",
  'what is': "what's",
};
