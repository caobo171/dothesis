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

// Credit packages shown on /credit. Each pack maps to a single Stripe checkout
// via /api/credit/purchase, which charges $0.10 per credit (linear). Multiple
// tiers exist so heavy users can grant themselves a larger one-shot purchase
// without clicking 'Buy' five times.
export type CreditPackage = {
  id: string;
  name: string;
  description: string;
  credit: number;
  price: number;
  old_price: number;
  highlight?: boolean;
};

export const PRICING_PACKAGES: CreditPackage[] = [
  {
    id: 'starter',
    name: 'Starter',
    description: 'Try the tool with a small grant.',
    credit: 50,
    price: 5,
    old_price: 5,
  },
  {
    id: 'standard',
    name: 'Standard',
    description: 'Most popular — covers regular use.',
    credit: 200,
    price: 20,
    old_price: 20,
    highlight: true,
  },
  {
    id: 'expert',
    name: 'Expert',
    description: 'For heavy use and bulk processing.',
    credit: 1000,
    price: 100,
    old_price: 100,
  },
];
