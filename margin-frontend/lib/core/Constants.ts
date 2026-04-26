const isProd = process.env.NODE_ENV === 'production';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
export const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:8001';

export const Code = {
  Success: 1,
  Error: 0,
  InvalidPassword: 2,
  InactiveAuth: 3,
  NotFound: 4,
  InvalidAuth: 5,
  InvalidInput: 6,
  InsufficientCredits: 7,
};

export const CreditCosts = {
  HUMANIZE_PER_100_WORDS: 1,
  AUTOCITE_PER_ANALYSIS: 3,
  PLAGIARISM_PER_CHECK: 5,
  AI_SCORE_CHECK: 1,
};
