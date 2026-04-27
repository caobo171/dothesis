// backend/src/api/routes/order/paddle.ts
//
// Paddle is client-side checkout (Paddle.js opens the modal directly). The
// only backend touchpoint is the webhook that delivers `transaction.completed`
// after the customer pays. We trust the customData we set when launching the
// checkout to tell us which user gets which credits.
//
// Required env:
//   PADDLE_NOTIFICATION_SECRET   (verifies webhook signatures)
//
// The signature is on the Paddle-Signature header. We do best-effort
// verification — if no secret is set we still accept the event but log a
// warning so dev setups don't get stuck.

import { Router } from 'express';
import bodyParser from 'body-parser';
import crypto from 'crypto';
import { Code } from '@/Constants';
import { UserModel } from '@/models/User';
import { CreditService } from '@/services/credit.service';

function verifyPaddleSignature(headerSig: string | undefined, rawBody: Buffer, secret: string): boolean {
  if (!headerSig || !secret) return false;
  // Header format: 'ts=<unix>;h1=<hex>'.
  const parts = Object.fromEntries(
    headerSig.split(';').map((kv) => kv.split('=').map((s) => s.trim())),
  ) as Record<string, string>;
  const ts = parts.ts;
  const sig = parts.h1;
  if (!ts || !sig) return false;
  const signed = `${ts}:${rawBody.toString('utf8')}`;
  const expected = crypto.createHmac('sha256', secret).update(signed).digest('hex');
  return crypto.timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(sig, 'hex'));
}

export default (router: Router) => {
  router.post(
    '/order/paddle/webhook',
    bodyParser.raw({ type: '*/*' }),
    async (req, res) => {
      const secret = process.env.PADDLE_NOTIFICATION_SECRET || '';
      const raw = req.body instanceof Buffer ? req.body : Buffer.from(req.body || '');

      if (secret) {
        const ok = verifyPaddleSignature(req.headers['paddle-signature'] as string, raw, secret);
        if (!ok) {
          return res.status(400).json({ code: Code.Error, message: 'Invalid signature' });
        }
      } else {
        console.warn('PADDLE_NOTIFICATION_SECRET not set — webhook accepted without signature verification');
      }

      let event: any;
      try {
        event = JSON.parse(raw.toString('utf8'));
      } catch {
        return res.status(400).json({ code: Code.Error, message: 'Invalid JSON' });
      }

      const eventType = event?.event_type;
      // We only care about completed transactions. Paddle also sends events
      // like transaction.created, transaction.paid, etc — ignore them.
      if (eventType !== 'transaction.completed') {
        return res.json({ code: Code.Success, data: { ignored: eventType } });
      }

      const tx = event.data || {};
      const customData = tx.custom_data || {};
      const userId = customData.user_id;
      const credits = Number(customData.credits || 0);
      const packageId = customData.packageId || 'unknown';
      const transactionId = tx.id;

      if (!userId || !credits || !transactionId) {
        return res.json({ code: Code.Error, message: 'Missing custom_data fields' });
      }

      try {
        const user = await UserModel.findById(userId);
        if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });
        await CreditService.addCredits(
          userId,
          credits,
          `Paddle: ${packageId}`,
          'paddle',
          transactionId
        );
        return res.json({ code: Code.Success, data: { granted: credits } });
      } catch (err: any) {
        console.error('Paddle webhook grant error:', err?.message || err);
        return res.json({ code: Code.Error, message: 'Grant failed' });
      }
    }
  );
};
