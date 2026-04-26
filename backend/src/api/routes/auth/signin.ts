import { Router } from 'express';
import passport from 'passport';
import jwt from 'jsonwebtoken';
import { Code } from '@/Constants';

const router = Router();

router.post('/signin', (req, res, next) => {
  passport.authenticate('signin', { session: false }, (err: any, user: any, info: any) => {
    if (err) return res.json({ code: Code.Error, message: err.message });
    if (!user) return res.json({ code: Code.InvalidPassword, message: info?.message || 'Login failed' });

    if (!user.emailVerified) {
      return res.json({
        code: Code.InactiveAuth,
        message: 'Your email is not verified, please check your inbox!',
        data: { email: user.email },
      });
    }

    const token = jwt.sign(
      { id: user._id, email: user.email, username: user.username },
      process.env.JWT_SECRET || 'margin_secret',
      { expiresIn: req.body.keep_login ? '30d' : '7d' }
    );

    user.lastLogin = new Date();
    user.save();

    return res.json({
      code: Code.Success,
      data: { token, user: user.secureRelease() },
    });
  })(req, res, next);
});

export default router;
