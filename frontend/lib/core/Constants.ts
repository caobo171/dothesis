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

// Credit packages shown on /credit. Mirrors the survify schema (same ids,
// same paddle ids) so a single env-of-secrets file works for both products.
// Backend /api/order/polar/create-checkout enforces the same map server-side.
export type CreditPackage = {
  id: string;
  name: string;
  price: number;
  old_price: number;
  credit: number;
  paddle_product_id?: string;
  paddle_price_id?: string;
};

export const PRICING_PACKAGES: CreditPackage[] = [
  {
    id: 'starter_package',
    name: 'Starter package',
    price: 9,
    old_price: 15,
    credit: 300,
    paddle_product_id: 'pro_01k7bxw7kdjbv6tpx4n4kn0as0',
    paddle_price_id: 'pri_01k7by8zxbe9exh7zdssjxtpdf',
  },
  {
    id: 'standard_package',
    name: 'Standard package',
    price: 19,
    old_price: 35,
    credit: 700,
    paddle_product_id: 'pro_01k7bqq13zhsrwxv5hdyxm3ndc',
    paddle_price_id: 'pri_01k7bqr7pacsjwqt70y0cvy9tr',
  },
  {
    id: 'expert_package',
    name: 'Expert package',
    price: 49,
    old_price: 100,
    credit: 2000,
    paddle_product_id: 'pro_01k7bqq13zhsrwxv5hdyxm3ndc',
    paddle_price_id: 'pri_01k7bqr7pacsjwqt70y0cvy9tr',
  },
];

// Survify-compatible payment provider configuration. Hardcoded primary
// provider (matches survify's pattern) — switch by editing this file.
// At runtime the Polar provider's status endpoint can downgrade to PayPal
// if Polar isn't configured.
export type PaymentProvider = 'polar' | 'paypal' | 'paddle';
export const PAYMENT_PROVIDER: PaymentProvider = 'polar';

export const IS_SANDBOX = process.env.NODE_ENV !== 'production';

// Public Paddle.js token. Same value as survify so the same Paddle
// dashboard config works against both products.
export const PADDLE_CLIENT_TOKEN = 'test_e38a19aec12f9a5b712c65b3901';

// Public PayPal client id. Same values as survify; sandbox/prod chosen by
// IS_SANDBOX. The corresponding PayPal SECRET key lives only on the backend.
export const PAYPAL_CLIENT_ID = IS_SANDBOX
  ? 'AWP0DWl85wvD-IpurSp8Zmpykr7fiZPq6nXP28llq5WaZ_uFIynCTzJB45LQIUNdnfkOioyKeTwOW2iN'
  : 'AfZQ_Kj-a495h2YynlS48RB38XX391s8HZqCtoZcgJ8skpn8uc4ehB0dx2QhAZx_pSmz8qh_nzdmCVNu';
