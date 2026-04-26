import { Router } from 'express';
import Stripe from 'stripe';
import { CreditService } from '@/services/credit.service';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
  apiVersion: '2023-10-16' as any,
});

export default (router: Router) => {
  router.post('/webhook/stripe', async (req: any, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event: Stripe.Event;

    try {
      if (webhookSecret && sig) {
        event = stripe.webhooks.constructEvent(req.rawBody, sig, webhookSecret);
      } else {
        event = req.body;
      }
    } catch (err: any) {
      console.error('Webhook signature verification failed:', err.message);
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    if (event.type === 'checkout.session.completed') {
      const session = event.data.object as Stripe.Checkout.Session;
      const userId = session.metadata?.userId;
      const credits = parseInt(session.metadata?.credits || '0', 10);

      if (userId && credits > 0) {
        await CreditService.addCredits(
          userId,
          credits,
          `Purchased ${credits} credits via Stripe`,
          'purchase',
          session.id
        );
        console.log(`Added ${credits} credits to user ${userId}`);
      }
    }

    return res.json({ received: true });
  });
};
