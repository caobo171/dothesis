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

export const Roles = {
  User: 'User',
  Admin: 'Admin',
};

export const CreditDirection = {
  Inbound: 'inbound',
  Outbound: 'outbound',
};

export const CreditStatus = {
  Pending: 'pending',
  Completed: 'completed',
  Failed: 'failed',
};

export const CreditCosts = {
  HUMANIZE_PER_100_WORDS: 1,
  AUTOCITE_PER_ANALYSIS: 3,
  PLAGIARISM_PER_CHECK: 5,
  AI_SCORE_CHECK: 1,
};

// Free signup grant. Trimmed (was 30) to match the new humanize rate
// (1 credit / 50 words, min 2). 10 credits = ~2 short humanize runs or
// 5 minimum-cost runs — enough to evaluate the product without
// burning a meaningful chunk of paid budget.
export const FREE_SIGNUP_CREDITS = 10;

export const JobStatus = {
  Pending: 'pending',
  Processing: 'processing',
  Completed: 'completed',
  Done: 'done',
  Failed: 'failed',
};

export const HumanizerTones = ['academic', 'casual', 'persuasive'] as const;
export const LengthModes = ['match', 'shorter', 'longer'] as const;
export const CitationStyles = ['apa', 'mla', 'chicago', 'harvard', 'ieee'] as const;
export const SourceTypes = ['paste', 'upload', 'url'] as const;
