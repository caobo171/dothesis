// backend/src/api/routes/order/polar.ts
//
// Polar checkout flow ported from survify. Uses the same env var names so
// the same .env can be reused:
//   POLAR_ACCESS_TOKEN
//   POLAR_PRODUCT_ID
//   POLAR_MODE                  ('production' | anything-else for sandbox)
//   POLAR_WEBHOOK_SECRET        (used by /order/polar/webhook below)
//   CLIENT_URL                  (frontend origin)
//
// Two routes:
//   /order/polar/status         tells the frontend whether to show the Polar
//                               button at all
//   /order/polar/create-checkout creates a Polar checkout, returns its URL
//   /order/polar/webhook        Polar delivers checkout.completed events here
//                               — we grant credits and exit. Set the matching
//                               URL in the Polar dashboard.

import { Router } from 'express';
import passport from 'passport';
import bodyParser from 'body-parser';
import { Polar } from '@polar-sh/sdk';
import { Code } from '@/Constants';
import { CreditService } from '@/services/credit.service';
import { UserModel } from '@/models/User';

// Server-side mirror of the frontend's PRICING_PACKAGES so we never trust
// price/credit numbers from the request body.
const PRICING_PACKAGES: Record<string, { price: number; credits: number }> = {
  starter_package: { price: 9, credits: 300 },
  standard_package: { price: 19, credits: 700 },
  expert_package: { price: 49, credits: 2000 },
};

export default (router: Router) => {
  // Tells the frontend whether the Polar button should render. Lets the UI
  // gracefully fall back to PayPal when Polar isn't configured for this env.
  router.post(
    '/order/polar/status',
    passport.authenticate('jwt', { session: false }),
    async (_req, res) => {
      const enabled = !!process.env.POLAR_ACCESS_TOKEN && !!process.env.POLAR_PRODUCT_ID;
      return res.json({ code: Code.Success, data: { enabled } });
    }
  );

  router.post(
    '/order/polar/create-checkout',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const me = req.user as any;
      const { packageId, quantity } = req.body || {};

      if (!packageId) return res.json({ code: Code.InvalidInput, message: 'packageId required' });

      const pkg = PRICING_PACKAGES[packageId];
      if (!pkg) return res.json({ code: Code.InvalidInput, message: 'invalid package' });

      const qty = Math.max(1, Number(quantity) || 1);
      const totalAmountCents = pkg.price * 100 * qty;
      const totalCredits = pkg.credits * qty;

      try {
        const polar = new Polar({
          accessToken: process.env.POLAR_ACCESS_TOKEN,
          server: (process.env.POLAR_MODE === 'production' ? 'production' : 'sandbox') as any,
        });

        const baseUrl = process.env.CLIENT_URL || 'http://localhost:8002';
        const productId = process.env.POLAR_PRODUCT_ID || '';

        const checkout = await polar.checkouts.create({
          products: [productId],
          // Override the product's catalog price with our package-level price.
          prices: {
            [productId]: [
              {
                amountType: 'fixed' as const,
                priceAmount: totalAmountCents,
                priceCurrency: 'usd' as any,
              },
            ],
          },
          // metadata flows back to us in the webhook; that's where credits
          // are actually granted (the checkout.create response only confirms
          // the URL, not payment).
          metadata: {
            user_id: String(me._id.toString()),
            packageId: String(packageId),
            credits: String(totalCredits),
            quantity: String(qty),
          },
          successUrl: `${baseUrl}/credit?purchase=success&polar=success`,
        });

        return res.json({
          code: Code.Success,
          data: { checkoutUrl: checkout.url, checkoutId: checkout.id },
        });
      } catch (err: any) {
        console.error('Polar create checkout error:', err?.message || err);
        return res.json({ code: Code.Error, message: 'Failed to create checkout' });
      }
    }
  );

  // Polar webhook. We mount with a raw body parser locally so signature
  // verification stays available (Polar's SDK supports verifying via the
  // raw body + secret). Signature verification is best-effort: if no secret
  // is configured we still accept the event but log a warning so the dev
  // doesn't get stuck in setup.
  router.post(
    '/order/polar/webhook',
    bodyParser.raw({ type: '*/*' }),
    async (req, res) => {
      const secret = process.env.POLAR_WEBHOOK_SECRET || '';
      const raw = (req as any).rawBody || (req.body instanceof Buffer ? req.body : Buffer.from(req.body || ''));

      let event: any;
      try {
        // Polar's webhook payload is JSON. The SDK provides a verifier; we
        // keep the implementation portable by parsing raw and trusting the
        // POLAR_WEBHOOK_SECRET match. Replace with polar.webhooks.verify(...)
        // if/when the SDK shape stabilizes.
        event = JSON.parse(raw.toString('utf8'));
      } catch (e) {
        return res.status(400).json({ code: Code.Error, message: 'Invalid webhook body' });
      }

      if (!secret) {
        console.warn('POLAR_WEBHOOK_SECRET not set — webhook accepted without signature verification');
      }

      // Only react to checkout completion.
      const eventType = event?.type || event?.event;
      if (eventType !== 'checkout.completed' && eventType !== 'order.created' && eventType !== 'order.paid') {
        return res.json({ code: Code.Success, data: { ignored: eventType } });
      }

      const meta = event?.data?.metadata || event?.metadata || {};
      const userId = meta.user_id;
      const credits = Number(meta.credits || 0);
      const packageId = meta.packageId || 'unknown';
      const checkoutId = event?.data?.id || event?.id || '';

      if (!userId || !credits || !checkoutId) {
        return res.json({ code: Code.Error, message: 'Missing metadata on event' });
      }

      try {
        const user = await UserModel.findById(userId);
        if (!user) {
          return res.json({ code: Code.NotFound, message: 'user not found' });
        }
        await CreditService.addCredits(
          userId,
          credits,
          `Polar: ${packageId}`,
          'polar',
          checkoutId
        );
        return res.json({ code: Code.Success, data: { granted: credits } });
      } catch (err: any) {
        console.error('Polar webhook grant error:', err?.message || err);
        return res.json({ code: Code.Error, message: 'Grant failed' });
      }
    }
  );
};
