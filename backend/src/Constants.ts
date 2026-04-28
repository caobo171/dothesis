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

// Sepay bank-transfer config. Vietnamese users see a QR + bank-info card on
// /credit instead of the international card-payment options. The memo must
// start with BANK_INFO.formatMsg so the Sepay webhook can recover the
// user.idcredit and route the credit grant.
export const BANK_INFO = {
  current: 'OCB' as const,
  // Prefix on every transfer memo. Webhook splits on this string to recover
  // the user's idcredit. Keep it short — Vietnamese banks truncate memos.
  formatMsg: 'DTH',
  providers: {
    OCB: {
      name: 'OCB - Orient Commercial Bank',
      number: 'SEPFFR148620',
    },
    VTB: {
      name: 'VTB - Vietinbank',
      number: '107868958175',
    },
  },
};

// VND-priced credit packs for Sepay flow. Mapped 1:1 with the USD packs
// (id and credit count match) so the rest of the app sees one set of
// products. Webhook matches the exact transferAmount to find the package.
export const PRICING_PACKAGES_VND: Array<{ id: string; price_vnd: number; credit: number }> = [
  { id: 'starter_package', price_vnd: 200_000, credit: 300 },
  { id: 'standard_package', price_vnd: 450_000, credit: 700 },
  { id: 'expert_package', price_vnd: 1_200_000, credit: 2000 },
];

export const HumanizerTones = ['academic', 'casual', 'persuasive'] as const;
export const LengthModes = ['match', 'shorter', 'longer'] as const;
export const CitationStyles = ['apa', 'mla', 'chicago', 'harvard', 'ieee'] as const;
export const SourceTypes = ['paste', 'upload', 'url'] as const;
