// backend/src/api/routes/order/paypal.ts
//
// PayPal order create + capture, ported from the survify codebase.
// Uses the same env var names so a single payments .env can be reused:
//   PAYPAL_CLIENT_ID / PAYPAL_SECRET_KEY                    (production)
//   PAYPAL_SANDBOX_CLIENT_ID / PAYPAL_SANDBOX_SECRET_KEY    (sandbox)
//   CLIENT_URL                                              (frontend origin)
//
// On capture, credits are granted directly via CreditService and a Credit
// transaction is recorded. Referral logic from survify is intentionally
// skipped — DoThesis doesn't have referId/referCredit fields.

import { Router } from 'express';
import passport from 'passport';
import axios from 'axios';
import { Code } from '@/Constants';
import { UserModel } from '@/models/User';
import { CreditService } from '@/services/credit.service';

const PAYPAL_API_URL =
  process.env.NODE_ENV === 'production'
    ? 'https://api-m.paypal.com'
    : 'https://api-m.sandbox.paypal.com';

async function getPayPalAccessToken(): Promise<string> {
  const isSandbox = process.env.NODE_ENV !== 'production';
  const clientId = isSandbox
    ? process.env.PAYPAL_SANDBOX_CLIENT_ID || process.env.PAYPAL_CLIENT_ID
    : process.env.PAYPAL_CLIENT_ID;
  const clientSecret = isSandbox
    ? process.env.PAYPAL_SANDBOX_SECRET_KEY || process.env.PAYPAL_SECRET_KEY
    : process.env.PAYPAL_SECRET_KEY;

  if (!clientId || !clientSecret) {
    throw new Error('PayPal credentials not configured (set PAYPAL_CLIENT_ID + PAYPAL_SECRET_KEY)');
  }

  const auth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');
  const response = await axios.post(
    `${PAYPAL_API_URL}/v1/oauth2/token`,
    'grant_type=client_credentials',
    {
      headers: {
        Authorization: `Basic ${auth}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }
  );
  return response.data.access_token;
}

export default (router: Router) => {
  // Authenticated — only signed-in users can create their own orders.
  router.post(
    '/order/paypal/create-order',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const me = req.user as any;
      const { packageId, price, credits, return_url, cancel_url } = req.body || {};

      if (!packageId || !price || !credits) {
        return res.json({ code: Code.InvalidInput, message: 'packageId, price, and credits required' });
      }

      const baseUrl = process.env.CLIENT_URL || 'http://localhost:8002';
      const finalReturnUrl = return_url || `${baseUrl}/credit/paypal-return`;
      const finalCancelUrl = cancel_url || `${baseUrl}/credit?purchase=cancel`;

      try {
        const accessToken = await getPayPalAccessToken();

        // custom_id carries everything we need on capture to identify the
        // beneficiary user and grant the right number of credits.
        const orderResponse = await axios.post(
          `${PAYPAL_API_URL}/v2/checkout/orders`,
          {
            intent: 'CAPTURE',
            purchase_units: [
              {
                amount: { currency_code: 'USD', value: String(price) },
                custom_id: JSON.stringify({
                  user_id: me._id.toString(),
                  packageId,
                  credits,
                }),
              },
            ],
            payment_source: {
              paypal: {
                experience_context: {
                  payment_method_preference: 'IMMEDIATE_PAYMENT_REQUIRED',
                  brand_name: 'DoThesis',
                  locale: 'en-US',
                  landing_page: 'LOGIN',
                  user_action: 'PAY_NOW',
                  return_url: finalReturnUrl,
                  cancel_url: finalCancelUrl,
                },
              },
            },
          },
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
          }
        );

        return res.json({ code: Code.Success, data: orderResponse.data });
      } catch (err: any) {
        console.error('PayPal create order error:', err?.response?.data || err.message);
        return res.json({
          code: Code.Error,
          message: 'Failed to create PayPal order',
        });
      }
    }
  );

  // Capture is invoked by the paypal-return page after the user approves.
  // We re-validate the order status with PayPal and (if newly captured)
  // grant credits via CreditService. Idempotent: a second call on an already
  // completed order returns success without double-granting.
  router.post(
    '/order/paypal/capture-order',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { orderId } = req.body || {};
      if (!orderId) return res.json({ code: Code.InvalidInput, message: 'orderId required' });

      try {
        const accessToken = await getPayPalAccessToken();

        const orderDetailsResponse = await axios.get(
          `${PAYPAL_API_URL}/v2/checkout/orders/${orderId}`,
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
          }
        );

        const orderDetails = orderDetailsResponse.data;

        // Already captured — return current status without re-granting.
        if (orderDetails.status === 'COMPLETED') {
          return res.json({
            code: Code.Success,
            data: orderDetails,
            message: 'Order already completed',
          });
        }

        if (orderDetails.status !== 'APPROVED') {
          return res.json({
            code: Code.Error,
            message: `Order not approved: ${orderDetails.status}`,
          });
        }

        const captureResponse = await axios.post(
          `${PAYPAL_API_URL}/v2/checkout/orders/${orderId}/capture`,
          {},
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
          }
        );

        const captureData = captureResponse.data;

        if (captureData.status === 'COMPLETED') {
          const captureUnit = captureData.purchase_units?.[0];
          const captureRecord = captureUnit?.payments?.captures?.[0];
          const customId = captureRecord?.custom_id || captureUnit?.custom_id;
          const captureId = captureRecord?.id;

          let customData: any = null;
          try {
            customData = JSON.parse(customId);
          } catch {
            console.error('Failed to parse PayPal custom_id:', customId);
          }

          if (customData && captureId) {
            const { user_id, credits, packageId } = customData;
            const user = await UserModel.findById(user_id);
            if (user) {
              // CreditService.addCredits takes (userId, amount, description, orderType, orderId).
              // We use captureId as orderId so re-runs of the capture endpoint
              // (e.g. user double-clicking) can dedupe via that field if needed.
              await CreditService.addCredits(
                user._id.toString(),
                Number(credits),
                `PayPal: ${packageId}`,
                'paypal',
                captureId
              );
            }
          }
        }

        return res.json({ code: Code.Success, data: captureData });
      } catch (err: any) {
        console.error('PayPal capture order error:', err?.response?.data || err.message);
        return res.json({ code: Code.Error, message: 'Failed to capture order' });
      }
    }
  );
};
