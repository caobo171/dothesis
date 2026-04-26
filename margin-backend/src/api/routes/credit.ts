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
