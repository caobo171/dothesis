import { Router } from 'express';
import passport from 'passport';
import Stripe from 'stripe';
import { Code } from '@/Constants';
import { CreditService } from '@/services/credit.service';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
  apiVersion: '2023-10-16' as any,
});

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

  router.post(
    '/credit/purchase',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { amount } = req.body; // credit amount to purchase

      if (!amount || amount < 10) {
        return res.json({ code: Code.InvalidInput, message: 'Minimum 10 credits' });
      }

      // $1 = 10 credits
      const priceInCents = Math.round((amount / 10) * 100);

      try {
        const session = await stripe.checkout.sessions.create({
          payment_method_types: ['card'],
          line_items: [
            {
              price_data: {
                currency: 'usd',
                product_data: { name: `${amount} Margin Credits` },
                unit_amount: priceInCents,
              },
              quantity: 1,
            },
          ],
          mode: 'payment',
          success_url: `${process.env.FRONTEND_URL || 'http://localhost:8002'}/humanizer?purchase=success`,
          cancel_url: `${process.env.FRONTEND_URL || 'http://localhost:8002'}/humanizer?purchase=cancel`,
          metadata: {
            userId: user._id.toString(),
            credits: amount.toString(),
          },
        });

        return res.json({ code: Code.Success, data: { url: session.url } });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );
};
