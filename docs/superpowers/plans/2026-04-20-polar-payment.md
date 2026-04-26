# Polar.sh Payment Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Polar.sh as the primary payment provider for credit purchases, with PayPal as secondary fallback.

**Architecture:** Backend creates ad-hoc Polar checkout sessions via `@polar-sh/sdk`. Polar webhook (`order.paid`) grants credits using the same idempotency pattern as PayPal. Frontend shows Polar as the primary button with PayPal below.

**Tech Stack:** `@polar-sh/sdk` (backend), Express.js routes, existing Fetch client (frontend)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `survify-backend/src/api/routes/order/polar.ts` | Checkout session creation endpoint |
| Create | `survify-backend/src/api/routes/webhook/polar.ts` | Webhook handler for `order.paid` |
| Modify | `survify-backend/src/api/routes/order/order.ts` | Register polar route |
| Modify | `survify-backend/src/api/routes/webhook/webhook.ts` | Register polar webhook |
| Modify | `survify-backend/.env.example` | Add Polar env vars |
| Modify | `survify-frontend/core/Constants.ts` | Add `PaymentProvider` type update |
| Modify | `survify-frontend/components/common/PricingPackages.tsx` | Polar primary button + PayPal fallback |

---

### Task 1: Install `@polar-sh/sdk` in backend

**Files:**
- Modify: `survify-backend/package.json`

- [ ] **Step 1: Install the SDK**

```bash
cd survify-backend && npm install @polar-sh/sdk
```

- [ ] **Step 2: Verify installation**

```bash
cd survify-backend && node -e "require('@polar-sh/sdk')" && echo "OK"
```

Expected: `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
cd survify-backend && git add package.json package-lock.json && git commit -m "chore: install @polar-sh/sdk"
```

---

### Task 2: Add Polar env vars to `.env.example`

**Files:**
- Modify: `survify-backend/.env.example`

- [ ] **Step 1: Add Polar environment variables**

Append to the end of `survify-backend/.env.example`:

```
# Polar.sh Payment
POLAR_ACCESS_TOKEN=
POLAR_WEBHOOK_SECRET=
POLAR_MODE=sandbox
```

- [ ] **Step 2: Commit**

```bash
git add survify-backend/.env.example && git commit -m "chore: add Polar.sh env vars to .env.example"
```

---

### Task 3: Create Polar checkout session route

**Files:**
- Create: `survify-backend/src/api/routes/order/polar.ts`

- [ ] **Step 1: Create the checkout route file**

Create `survify-backend/src/api/routes/order/polar.ts`:

```typescript
import { Router } from "express"
import multer from "multer"
import { Polar } from "@polar-sh/sdk"
import BaseError from "@/packages/error/error"
import { wrapAsync } from "@/utils/helper"
import { UserModel } from "@/models/User"

const PRICING_PACKAGES: Record<string, { price: number; credit: number; name: string }> = {
    starter_package: { price: 9, credit: 300, name: 'Starter package' },
    standard_package: { price: 19, credit: 700, name: 'Standard package' },
    expert_package: { price: 49, credit: 2000, name: 'Expert package' },
}

function getPolarClient() {
    return new Polar({
        accessToken: process.env.POLAR_ACCESS_TOKEN,
        server: (process.env.POLAR_MODE === 'production' ? 'production' : 'sandbox') as any,
    })
}

export default (route: Router) => {
    route.post('/polar/create-checkout', multer({}).fields([]),
        wrapAsync(async (req, res) => {
            const { packageId, quantity: rawQty, user_id, credit_id } = req.body;

            if (!packageId || !user_id || !credit_id) {
                return res.status(400).send(new BaseError("MISSING_PARAMS", -1).release());
            }

            const pkg = PRICING_PACKAGES[packageId];
            if (!pkg) {
                return res.status(400).send(new BaseError("INVALID_PACKAGE", -1).release());
            }

            const quantity = Math.max(1, Math.min(99, Number(rawQty) || 1));
            const totalPrice = pkg.price * quantity;
            const totalCredits = pkg.credit * quantity;

            // Verify user exists
            const user = await UserModel.findOne({ idcredit: credit_id });
            if (!user || user.id != user_id) {
                return res.status(400).send(new BaseError("INVALID_USER", -1).release());
            }

            const baseUrl = process.env.CLIENT_URL || 'http://localhost:7002';

            try {
                const polar = getPolarClient();

                const checkout = await polar.checkouts.create({
                    productPriceId: undefined as any,
                    amount: totalPrice * 100, // cents
                    currency: 'usd',
                    successUrl: `${baseUrl}/credit?polar=success`,
                    metadata: {
                        user_id,
                        credit_id: String(credit_id),
                        packageId,
                        credits: String(totalCredits),
                        quantity: String(quantity),
                    },
                });

                return res.status(200).send({
                    code: BaseError.Code.SUCCESS,
                    data: {
                        checkoutUrl: checkout.url,
                        checkoutId: checkout.id,
                    }
                });
            } catch (error) {
                console.error('Polar create checkout error:', error);
                return res.status(500).send(new BaseError("CREATE_CHECKOUT_FAILED", -1).release());
            }
        })
    );
}
```

- [ ] **Step 2: Register the route in the order router**

In `survify-backend/src/api/routes/order/order.ts`, add the import and registration:

Add import at the top (after the `paypal` import line):
```typescript
import polar from './polar';
```

Add registration call (after the `paypal(route);` line):
```typescript
polar(route);
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd survify-backend && npx tsc --noEmit
```

Expected: No errors (or only pre-existing errors unrelated to our changes).

- [ ] **Step 4: Commit**

```bash
git add survify-backend/src/api/routes/order/polar.ts survify-backend/src/api/routes/order/order.ts && git commit -m "feat: add Polar.sh checkout session creation route"
```

---

### Task 4: Create Polar webhook handler

**Files:**
- Create: `survify-backend/src/api/routes/webhook/polar.ts`

- [ ] **Step 1: Create the webhook handler**

Create `survify-backend/src/api/routes/webhook/polar.ts`:

```typescript
import { Router } from "express"
import multer from "multer"
import { Polar } from "@polar-sh/sdk"
import BaseError from "@/packages/error/error"
import { wrapAsync } from "@/utils/helper"
import { UserModel } from "@/models/User"
import { CREDIT_DIRECTION, CREDIT_STATUS, REFER_PERCENT } from "@/Constants"
import { CreditModel } from "@/models/Credit"
import SocketServer from "@/services/socket/server"

function getPolarClient() {
    return new Polar({
        accessToken: process.env.POLAR_ACCESS_TOKEN,
        server: (process.env.POLAR_MODE === 'production' ? 'production' : 'sandbox') as any,
    })
}

export default (route: Router) => {
    route.post('/83868/polar', multer({}).fields([]),
        wrapAsync(async (req, res) => {
            const eventType = req.body.type || req.body.event_type;

            console.log('Polar Webhook received:', eventType);

            // Only process order.paid events
            if (eventType !== 'order.paid') {
                console.log('Polar Webhook - Ignoring event:', eventType);
                return res.status(200).send(new BaseError("OK", 1).release());
            }

            const order = req.body.data;
            const metadata = order?.metadata || {};
            const { user_id, credit_id, credits, packageId } = metadata;
            const eventId = req.body.id || req.body.event_id;
            const grandTotal = order?.amount ? (order.amount / 100).toString() : '0';

            if (!credits || !credit_id || !user_id || !eventId) {
                console.error('Polar Webhook - Missing required data:', { credits, credit_id, user_id, eventId });
                return res.status(200).send(new BaseError("INVALID_DATA", 1).release());
            }

            try {
                let user = await UserModel.findOne({ idcredit: Number(credit_id) });
                if (!user || user.id != user_id) {
                    console.error('Polar Webhook - User not found or mismatch:', { credit_id, user_id });
                    return res.status(200).send(new BaseError("INVALID_USER", 1).release());
                }

                // Idempotency check
                let existingCredit = await CreditModel.findOne({ referenceId: eventId });
                if (existingCredit) {
                    console.log('Polar Webhook - Already processed:', eventId);
                    return res.status(200).send(new BaseError("DUPLICATE", 1).release());
                }

                try {
                    console.log("Polar - user.credit", user.credit);
                    console.log("Polar - credits", credits);
                    console.log("Polar - grandTotal", grandTotal);

                    user.credit = user.credit + Number(credits);
                    user.markModified('credit');
                    await user.save();

                    console.log("Polar - user.credit after", user.credit);

                    console.log("Polar - Start Create Credit history");
                    let credit_db: any = {};
                    credit_db.amount = grandTotal;
                    credit_db.direction = CREDIT_DIRECTION.IN;
                    credit_db.owner = user.email;
                    credit_db.owner_id = user.id;
                    credit_db.status = CREDIT_STATUS.SUCCESS;
                    credit_db.referenceId = eventId;
                    credit_db.data = req.body;
                    credit_db.referId = user.referId || 0;
                    credit_db.referPercent = REFER_PERCENT;
                    credit_db.referAmount = Number(grandTotal) * REFER_PERCENT / 100;
                    credit_db.provider = 'polar';

                    await CreditModel.create(credit_db);

                    SocketServer.getInstance().emitToUser(user.id, 'credit_update', {
                        user_id: user.id,
                        credit: user.credit
                    });

                    if (user.referId && user.referId != user.id) {
                        let refer_user = await UserModel.findById(user.referId);
                        if (refer_user) {
                            refer_user.referCredit = (refer_user.referCredit || 0) + Number(credit_db.referAmount);
                            await refer_user.save();
                        }
                    }
                } catch (error) {
                    console.error("Polar - Error saving credit:", error);
                    throw error;
                }
            } catch (error) {
                console.error('Polar Error:', error);
            }

            console.log("Polar - Credit added successfully");

            return res.status(200).send({
                message: "Credit added successfully",
                code: BaseError.Code.SUCCESS
            });
        })
    );
}
```

- [ ] **Step 2: Register the webhook in the webhook router**

In `survify-backend/src/api/routes/webhook/webhook.ts`, add the import and registration:

Replace the entire file content with:
```typescript
import { Router } from "express";
import credit from "./credit";
import paypal from "./paypal";
import polar from "./polar";

export default (app: Router) => {
    const route = Router();

    app.use('/h00k', route);

    credit(route);
    paypal(route);
    polar(route);
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd survify-backend && npx tsc --noEmit
```

Expected: No errors (or only pre-existing errors unrelated to our changes).

- [ ] **Step 4: Commit**

```bash
git add survify-backend/src/api/routes/webhook/polar.ts survify-backend/src/api/routes/webhook/webhook.ts && git commit -m "feat: add Polar.sh webhook handler for order.paid events"
```

---

### Task 5: Update frontend Constants

**Files:**
- Modify: `survify-frontend/core/Constants.ts`

- [ ] **Step 1: Update the PaymentProvider type and default**

In `survify-frontend/core/Constants.ts`, change the `PaymentProvider` type and default:

Find:
```typescript
export type PaymentProvider = 'paddle' | 'paypal';

export const PAYMENT_PROVIDER: PaymentProvider = 'paypal';
```

Replace with:
```typescript
export type PaymentProvider = 'polar' | 'paypal' | 'paddle';

export const PAYMENT_PROVIDER: PaymentProvider = 'polar';
```

- [ ] **Step 2: Commit**

```bash
git add survify-frontend/core/Constants.ts && git commit -m "feat: set Polar.sh as default payment provider"
```

---

### Task 6: Update PricingPackages component

**Files:**
- Modify: `survify-frontend/components/common/PricingPackages.tsx`

- [ ] **Step 1: Rewrite PricingPackages to support Polar as primary + PayPal fallback**

Replace the entire content of `survify-frontend/components/common/PricingPackages.tsx` with:

```tsx
'use client'
import { FC, useState, useEffect } from 'react'
import { useMe } from '@/hooks/user';
import { PRICING_PACKAGES, PADDLE_CLIENT_TOKEN, PAYMENT_PROVIDER, IS_SANDBOX } from '@/core/Constants'
import Fetch from '@/lib/core/fetch/Fetch'
import { DollarSign, Plus, Award, Ticket, Minus } from 'lucide-react'
import { usePostHog } from 'posthog-js/react'

// Declare Paddle types
declare global {
  interface Window {
    Paddle?: any;
  }
}

interface PricingPackagesProps {
  compact?: boolean;
  onSuccess?: () => void;
}

const PricingPackages: FC<PricingPackagesProps> = ({ compact = false, onSuccess }) => {
  const [providerLoaded, setProviderLoaded] = useState(PAYMENT_PROVIDER === 'paypal' || PAYMENT_PROVIDER === 'polar');
  const [processingPackage, setProcessingPackage] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>(() =>
    Object.fromEntries(PRICING_PACKAGES.map(pkg => [pkg.id, 1]))
  );
  const me = useMe();
  const posthog = usePostHog();

  const updateQuantity = (pkgId: string, delta: number) => {
    setQuantities(prev => ({
      ...prev,
      [pkgId]: Math.max(1, Math.min(99, (prev[pkgId] || 1) + delta))
    }));
  };

  useEffect(() => {
    if (!me?.data) {
      return;
    }

    if (PAYMENT_PROVIDER === 'paddle') {
      if (window.Paddle) {
        setProviderLoaded(true);
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://cdn.paddle.com/paddle/v2/paddle.js';
      script.async = true;
      script.onload = () => {
        if (window.Paddle) {
          if (IS_SANDBOX) {
            window.Paddle.Environment.set('sandbox');
          }
          window.Paddle.Initialize({
            token: PADDLE_CLIENT_TOKEN,
            pwCustomer: 'ctm_' + me?.data?.id,
          });
          setProviderLoaded(true);
        }
      };
      document.body.appendChild(script);
    }
  }, [me]);

  const handlePaddleCheckout = (pkg: typeof PRICING_PACKAGES[0]) => {
    if (!window.Paddle) {
      console.error('Paddle is not loaded yet');
      return;
    }

    const qty = quantities[pkg.id] || 1;
    const eventProps = { package_id: pkg.id, package_name: pkg.name, quantity: qty, total_price: pkg.price * qty, total_credits: pkg.credit * qty, provider: 'paddle' };
    posthog?.capture('checkout_started', eventProps);

    window.Paddle.Checkout.open({
      items: [
        {
          priceId: pkg.paddle_price_id,
          quantity: qty
        }
      ],
      customData: {
        user_id: me?.data?.id,
        credit_id: me?.data?.idcredit,
        packageId: pkg.id,
        credits: pkg.credit * qty,
        quantity: qty
      },
      settings: {
        successUrl: window.location.href,
      },
      eventCallback: (event: any) => {
        if (event.name === 'checkout.completed') {
          posthog?.capture('payment_completed', eventProps);
          console.log('Payment completed:', event.data);
          window.Paddle.Checkout.close();
          onSuccess?.();
          window.location.reload();
        } else if (event.name === 'checkout.closed') {
          posthog?.capture('checkout_abandoned', eventProps);
          console.log('Checkout closed');
        }
      }
    });
  };

  const handlePolarCheckout = async (pkg: typeof PRICING_PACKAGES[0]) => {
    setProcessingPackage(pkg.id);
    const qty = quantities[pkg.id] || 1;
    const eventProps = { package_id: pkg.id, package_name: pkg.name, quantity: qty, total_price: pkg.price * qty, total_credits: pkg.credit * qty, provider: 'polar' };
    posthog?.capture('checkout_started', eventProps);

    try {
      const response = await Fetch.postWithAccessToken('/api/order/polar/create-checkout', {
        packageId: pkg.id,
        quantity: qty,
        user_id: me?.data?.id,
        credit_id: me?.data?.idcredit
      });

      const data = response.data as any;

      if (data.code !== 1 || !data.data?.checkoutUrl) {
        posthog?.capture('checkout_failed', { ...eventProps, error: 'Failed to create Polar checkout' });
        throw new Error('Failed to create Polar checkout');
      }

      posthog?.capture('checkout_redirected_to_polar', eventProps);
      window.location.href = data.data.checkoutUrl;
    } catch (error) {
      console.error('Polar checkout error:', error);
      posthog?.capture('checkout_failed', { ...eventProps, error: String(error) });
      setProcessingPackage(null);
    }
  };

  const handlePayPalCheckout = async (pkg: typeof PRICING_PACKAGES[0]) => {
    setProcessingPackage(pkg.id);
    const qty = quantities[pkg.id] || 1;
    const eventProps = { package_id: pkg.id, package_name: pkg.name, quantity: qty, total_price: pkg.price * qty, total_credits: pkg.credit * qty, provider: 'paypal' };
    posthog?.capture('checkout_started', eventProps);

    try {
      const createResponse = await Fetch.postWithAccessToken('/api/order/paypal/create-order', {
        packageId: pkg.id,
        price: pkg.price * qty,
        credits: pkg.credit * qty,
        quantity: qty,
        user_id: me?.data?.id,
        credit_id: me?.data?.idcredit
      });

      const createData = createResponse.data as any;

      if (createData.code !== 1 || !createData.data?.id) {
        posthog?.capture('checkout_failed', { ...eventProps, error: 'Failed to create PayPal order' });
        throw new Error('Failed to create PayPal order');
      }

      posthog?.capture('checkout_redirected_to_paypal', eventProps);

      const approvalUrl = createData.data.links?.find((link: any) =>
        link.rel === 'payer-action' || link.rel === 'approve'
      )?.href;
      if (approvalUrl) {
        window.location.href = approvalUrl;
      } else {
        throw new Error('No approval URL found');
      }
    } catch (error) {
      console.error('PayPal checkout error:', error);
      posthog?.capture('checkout_failed', { ...eventProps, error: String(error) });
      setProcessingPackage(null);
    }
  };

  const handlePrimaryCheckout = (pkg: typeof PRICING_PACKAGES[0]) => {
    if (!providerLoaded) {
      console.error('Payment provider is not loaded yet');
      return;
    }

    if (!me?.data?.id) {
      console.error('User data not available');
      return;
    }

    if (PAYMENT_PROVIDER === 'polar') {
      handlePolarCheckout(pkg);
    } else if (PAYMENT_PROVIDER === 'paddle') {
      handlePaddleCheckout(pkg);
    } else {
      handlePayPalCheckout(pkg);
    }
  };

  const getPackageIcon = (id: string) => {
    const iconSize = compact ? 'w-6 h-6' : 'w-8 h-8';
    switch (id) {
      case 'starter_package':
        return <DollarSign className={`${iconSize} text-primary-600`} />;
      case 'standard_package':
        return <Plus className={`${iconSize} text-primary-600`} />;
      case 'expert_package':
        return <Award className={`${iconSize} text-primary-600`} />;
      default:
        return <Ticket className={`${iconSize} text-primary-600`} />;
    }
  };

  const getPackageDescription = (id: string) => {
    switch (id) {
      case 'starter_package':
        return 'Ideal for trying product with basic feature Have a quick start.';
      case 'standard_package':
        return 'Ideal for using all service with standard need & quality';
      case 'expert_package':
        return 'Best Price for professional using & share with your friend';
      default:
        return '';
    }
  };

  return (
    <div className="w-full">
      {/* Pricing Cards */}
      <div className={`grid grid-cols-1 ${compact ? 'md:grid-cols-3 gap-4' : 'md:grid-cols-2 lg:grid-cols-3 gap-6'} mb-6`}>
        {PRICING_PACKAGES.map((pkg) => {
          const qty = quantities[pkg.id] || 1;
          const totalPrice = pkg.price * qty;
          const totalCredits = pkg.credit * qty;

          return (
            <div
              key={pkg.id}
              className={`bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow duration-300 ${compact ? 'p-4' : 'p-6'} flex flex-col border border-gray-100`}
            >
              {/* Icon */}
              <div className={`bg-primary-50 rounded-xl ${compact ? 'w-10 h-10 mb-3' : 'w-16 h-16 mb-4'} flex items-center justify-center`}>
                {getPackageIcon(pkg.id)}
              </div>

              {/* Package Name */}
              <h3 className={`${compact ? 'text-base' : 'text-xl'} font-semibold text-gray-900 mb-1 capitalize`}>
                {pkg.name}
              </h3>

              {/* Description */}
              {!compact && (
                <p className="text-sm text-gray-600 mb-4 flex-grow">
                  {getPackageDescription(pkg.id)}
                </p>
              )}

              {/* Unit Price */}
              <div className={`flex items-center gap-2 ${compact ? 'mb-2' : 'mb-3'}`}>
                <span className={`${compact ? 'text-2xl' : 'text-3xl'} font-bold text-gray-900`}>
                  ${pkg.price}
                </span>
                <span className={`${compact ? 'text-sm' : 'text-lg'} text-gray-400 line-through`}>
                  ${pkg.old_price}
                </span>
                <span className="text-xs text-gray-400">/ pack</span>
              </div>

              {/* Credits per pack */}
              <div className={`flex items-center gap-2 ${compact ? 'mb-3' : 'mb-4'}`}>
                <div className={`flex items-center gap-1.5 ${compact ? 'px-2 py-1' : 'px-3 py-1.5'} bg-primary-50 border border-primary-200 rounded-full`}>
                  <Ticket className={`${compact ? 'w-4 h-4' : 'w-5 h-5'} text-primary-600`} />
                  <span className={`text-primary-600 font-semibold ${compact ? 'text-xs' : 'text-sm'}`}>
                    {pkg.credit.toLocaleString()} Credit / pack
                  </span>
                </div>
              </div>

              {/* Quantity Selector */}
              <div className={`flex items-center justify-between ${compact ? 'mb-3' : 'mb-4'} bg-gray-50 rounded-lg p-2`}>
                <span className={`${compact ? 'text-xs' : 'text-sm'} font-medium text-gray-600`}>Quantity</span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => updateQuantity(pkg.id, -1)}
                    disabled={qty <= 1}
                    className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <Minus className="w-3.5 h-3.5 text-gray-600" />
                  </button>
                  <span className={`${compact ? 'text-sm' : 'text-base'} font-semibold text-gray-900 w-8 text-center`}>
                    {qty}
                  </span>
                  <button
                    type="button"
                    onClick={() => updateQuantity(pkg.id, 1)}
                    disabled={qty >= 99}
                    className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5 text-gray-600" />
                  </button>
                </div>
              </div>

              {/* Total Summary */}
              {qty > 1 && (
                <div className={`${compact ? 'mb-3' : 'mb-4'} bg-primary-50 rounded-lg p-2`}>
                  <div className="flex justify-between items-center">
                    <span className={`${compact ? 'text-xs' : 'text-sm'} text-gray-600`}>Total</span>
                    <div className="text-right">
                      <span className={`${compact ? 'text-base' : 'text-lg'} font-bold text-primary-700`}>${totalPrice}</span>
                      <span className={`${compact ? 'text-xs' : 'text-xs'} text-primary-600 ml-2`}>
                        ({totalCredits.toLocaleString()} Credit)
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Primary Payment Button (Polar) */}
              <button
                onClick={() => handlePrimaryCheckout(pkg)}
                disabled={!providerLoaded || processingPackage === pkg.id}
                className={`w-full bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white font-medium ${compact ? 'py-2 text-sm' : 'py-2.5'} px-4 rounded-lg transition-colors duration-200`}
              >
                {processingPackage === pkg.id ? 'Processing...' : qty > 1 ? `Pay $${totalPrice}` : 'Buy Now'}
              </button>

              {/* Secondary PayPal Link (shown when Polar is primary) */}
              {PAYMENT_PROVIDER === 'polar' && (
                <button
                  onClick={() => handlePayPalCheckout(pkg)}
                  disabled={processingPackage === pkg.id}
                  className={`w-full text-gray-500 hover:text-gray-700 font-medium ${compact ? 'py-1 text-xs' : 'py-1.5 text-sm'} mt-1 transition-colors duration-200`}
                >
                  Or pay with PayPal
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Refund Policy Section */}
      {!compact && (
        <div className="bg-primary-50 rounded-xl p-6 text-center">
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Refund 100%
          </h2>
          <p className="text-sm text-gray-700 mb-1">
            We commit to refund 100% of credit fee if the tool is not successful or not as committed.
          </p>
          <p className="text-sm text-gray-600">
            For more information. View our{' '}
            <a href="#" className="text-primary-600 hover:text-primary-700 font-medium">
              Detail Policy
            </a>
          </p>
        </div>
      )}
    </div>
  );
}

export default PricingPackages;
```

- [ ] **Step 2: Commit**

```bash
git add survify-frontend/components/common/PricingPackages.tsx && git commit -m "feat: add Polar.sh as primary payment with PayPal fallback in PricingPackages"
```

---

### Task 7: Handle Polar success/cancel on credit page

**Files:**
- Modify: `survify-frontend/app/(inapp)/credit/_components/Credit.tsx`

- [ ] **Step 1: Add query param handling for Polar success/cancel**

In `survify-frontend/app/(inapp)/credit/_components/Credit.tsx`, add `useSearchParams` handling:

Replace the imports at the top:
```tsx
'use client'
import { FC, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useMe } from '@/hooks/user';
import { useMyForms } from '@/hooks/form';
import { useMyOrders } from '@/hooks/order';
import { Ticket, FileText, ShoppingCart, Mail, Hash, CheckCircle } from 'lucide-react';
import PricePackages from './PricePackages';
```

Add after `const orders = ...` line and before the `return`:
```tsx
    const searchParams = useSearchParams();
    const polarStatus = searchParams.get('polar');
```

Add a success banner inside the JSX, right after the opening `<div className="max-w-5xl mx-auto"` div and before the `{/* Compact Header Row */}` comment:
```tsx
                {polarStatus === 'success' && (
                    <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
                        <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                        <p className="text-sm text-green-800">
                            Payment successful! Your credits will be added shortly.
                        </p>
                    </div>
                )}
```

- [ ] **Step 2: Commit**

```bash
git add survify-frontend/app/(inapp)/credit/_components/Credit.tsx && git commit -m "feat: show Polar payment success banner on credit page"
```

---

### Task 8: Verify full build compiles

**Files:** None (verification only)

- [ ] **Step 1: Verify backend compiles**

```bash
cd survify-backend && npx tsc --noEmit
```

Expected: No new errors.

- [ ] **Step 2: Verify frontend compiles**

```bash
cd survify-frontend && npx next build
```

Expected: Build succeeds (or only pre-existing warnings).

- [ ] **Step 3: Final commit if any fixes needed**

If compilation revealed issues, fix them and commit:
```bash
git add -A && git commit -m "fix: resolve compilation issues from Polar integration"
```
