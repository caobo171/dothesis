import { Router } from 'express';
import jwt from 'jsonwebtoken';
import { UserModel } from '@/models/User';
import { Mailer } from '@/packages/mail/mail';
import { Code } from '@/Constants';

const router = Router();

router.post('/resend.email', async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.json({ code: Code.InvalidInput, message: 'Email is required' });
    }

    const user = await UserModel.findOne({ email: email.toLowerCase() });
    if (!user) {
      return res.json({ code: Code.Error, message: 'User not found' });
    }

    if (user.emailVerified) {
      return res.json({ code: Code.Error, message: 'Email already verified' });
    }

    const verifyToken = jwt.sign(
      { email: user.email, username: user.username },
      process.env.JWT_VERIFY_KEY || 'margin_verify_secret',
      { expiresIn: '24h' }
    );

    await Mailer.sendVerificationEmail(user.email, user.username, verifyToken);

    return res.json({ code: Code.Success, message: 'Verification email sent' });
  } catch (err: any) {
    return res.json({ code: Code.Error, message: err.message });
  }
});

export default router;
