import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';

export default (router: Router) => {
  router.post('/me', passport.authenticate('jwt', { session: false }), (req, res) => {
    const user = req.user as any;
    if (!user) return res.json({ code: Code.InvalidAuth, message: 'Not authenticated' });
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });
};
