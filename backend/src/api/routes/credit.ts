// backend/src/api/routes/credit.ts
//
// Credit balance + history. Purchase flow has moved to /order/paypal,
// /order/polar, /order/paddle to match the survify payment stack — Stripe
// is no longer the credit-purchase path. Existing user-facing endpoints
// preserved here so nothing in the rest of the app needs to change.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { CreditService } from '@/services/credit.service';

export default (router: Router) => {
  router.post(
    '/credit/balance',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const balance = await CreditService.getBalance(user._id.toString());
      return res.json({ code: Code.Success, data: { balance } });
    }
  );

  router.post(
    '/credit/history',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const history = await CreditService.getHistory(user._id.toString());
      return res.json({ code: Code.Success, data: history });
    }
  );
};
