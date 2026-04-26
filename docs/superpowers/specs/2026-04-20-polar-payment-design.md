# Polar.sh Payment Integration Design

## Overview

Add Polar.sh as the primary payment provider for credit purchases, using ad-hoc checkout sessions (no pre-created products on Polar dashboard). PayPal remains as a secondary fallback. Paddle code stays in place but is hidden from the UI.

## Architecture

The integration follows the same pattern as the existing PayPal flow:

1. Frontend calls backend to create a checkout session
2. Backend creates a Polar.sh checkout with dynamic pricing via `@polar-sh/sdk`
3. User completes payment on Polar.sh hosted checkout page
4. Polar.sh sends `order.paid` webhook to backend
5. Backend verifies signature, grants credits, logs transaction, emits socket notification

## Backend Changes

### New Files

**`src/api/routes/order/polar.ts`** — Checkout session creation route

- `POST /api/order/polar/create-checkout`
- Accepts: `{ packageId }` (authenticated user)
- Looks up package from `PRICING_PACKAGES` constant
- Creates a Polar checkout session with ad-hoc pricing:
  - `priceAmount`: package price in cents
  - `priceCurrency`: "usd"
  - `successUrl`: `{FRONTEND_URL}/credit?polar=success`
  - `cancelUrl`: `{FRONTEND_URL}/credit?polar=cancel`
  - `metadata`: `{ userId, idcredit, packageId, credits }`
- Returns `{ checkoutUrl }` to frontend

**`src/api/routes/webhook/polar.ts`** — Webhook handler

- Endpoint: `POST /h00k/83868/polar`
- Verifies webhook signature using Polar SDK's `validateEvent()`
- Handles events:
  - `order.paid`: Grant credits to user
  - `order.refunded`: Log refund (no automatic credit revocation — manual review)
- Idempotency: Uses Polar event ID as `referenceId` in Credit model to prevent duplicates
- Credit granting flow (mirrors PayPal webhook):
  1. Extract `userId`, `idcredit`, `packageId`, `credits` from order metadata
  2. Verify user exists and `idcredit` matches
  3. Check `referenceId` not already processed
  4. Add credits to user's balance
  5. Create Credit record (direction: "inbound", provider: "polar", status: "completed")
  6. Calculate 15% referral commission if user has `referId`
  7. Emit `credit_update` via Socket.io

### Modified Files

**`src/api/routes/order/order.ts`** — Register polar routes in the order router

**`src/api/routes/webhook/webhook.ts`** — Register polar webhook route

**`src/Constants.ts`** — Add:
- `POLAR_ACCESS_TOKEN` (from env)
- `POLAR_WEBHOOK_SECRET` (from env)
- `POLAR_MODE` (from env, "sandbox" | "production")

**`.env.example`** — Add:
- `POLAR_ACCESS_TOKEN=`
- `POLAR_WEBHOOK_SECRET=`
- `POLAR_MODE=sandbox`

### Dependencies

- `@polar-sh/sdk` — Polar.sh TypeScript SDK (npm install)

## Frontend Changes

### Modified Files

**`components/common/PricingPackages.tsx`**

- Each pricing card gets a primary "Buy Now" button that triggers Polar.sh checkout
- Below the primary button: "Or pay with PayPal" text link
- Paddle buttons hidden (code remains)
- On click: POST to `/api/order/polar/create-checkout`, then `window.location.href = checkoutUrl`

**`app/(inapp)/credit/page.tsx`**

- Handle `?polar=success` and `?polar=cancel` query params
- Show success/cancel toast notification
- Success: Refresh credit balance (socket event will also update it)

**`core/Constants.ts`**

- No changes needed for Polar (ad-hoc pricing uses existing `PRICING_PACKAGES` array)
- Paddle product IDs remain but are unused

## Data Flow

```
User clicks "Buy Now" on Starter package ($9, 300 credits)
  → Frontend POST /api/order/polar/create-checkout { packageId: "starter_package" }
  → Backend authenticates user via JWT
  → Backend looks up package: { price: 9, credit: 300 }
  → Backend calls polar.checkouts.create({
      productPriceId: null,  // ad-hoc pricing
      amount: 900,           // cents
      currency: "usd",
      successUrl: "https://app.survify.io/credit?polar=success",
      metadata: { userId: "abc123", idcredit: 42, packageId: "starter_package", credits: 300 }
    })
  → Returns { checkoutUrl: "https://checkout.polar.sh/..." }
  → Frontend redirects user to checkoutUrl
  → User completes payment on Polar.sh
  → Polar redirects user to successUrl
  → Polar sends POST /h00k/83868/polar with order.paid event
  → Backend verifies webhook signature
  → Backend checks referenceId not duplicate
  → Backend adds 300 credits to user
  → Backend creates Credit record
  → Backend calculates referral commission (if applicable)
  → Backend emits socket credit_update
  → Frontend shows updated balance
```

## Security

- **Webhook signature verification**: All webhook payloads verified via Polar SDK before processing
- **Idempotency**: Polar event ID stored as `referenceId` in Credit model — duplicate events are no-ops
- **User validation**: `idcredit` from metadata must match user's current `idcredit` value
- **Environment isolation**: `POLAR_MODE` env var controls sandbox vs production API endpoint
- **Secret management**: Access token and webhook secret stored only in env vars, never exposed to client

## Credit Record Schema

Each successful Polar payment creates a Credit document:

```typescript
{
  amount: 300,                    // credits granted
  direction: "inbound",
  owner: "user@email.com",
  status: "completed",
  description: "Polar payment - Starter package",
  referId: "referrer-user-id",    // if applicable
  orderType: "survify",
  orderId: "polar-order-id",
  referPercent: 15,
  referAmount: 45,                // 15% of 300
  referenceId: "polar-event-id",  // for idempotency
  provider: "polar",
  data: { /* full Polar webhook payload */ }
}
```

## UI Layout (per pricing card)

```
┌─────────────────────────┐
│  Starter Package        │
│  300 credits            │
│  $9.00                  │
│                         │
│  ┌───────────────────┐  │
│  │    Buy Now        │  │  ← Primary button (Polar.sh)
│  └───────────────────┘  │
│                         │
│  Or pay with PayPal     │  ← Secondary text link
└─────────────────────────┘
```

## Out of Scope

- Paddle removal (kept as hidden/disabled code)
- Stripe integration
- Subscription/recurring billing via Polar
- Automatic credit revocation on refunds (logged for manual review)
