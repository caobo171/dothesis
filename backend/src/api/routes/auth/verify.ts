import { Router } from 'express';
import jwt from 'jsonwebtoken';
import { UserModel } from '@/models/User';
import { Code } from '@/Constants';

const router = Router();

router.post('/verify', async (req, res) => {
  const { token } = req.body;

  try {
    const decoded: any = jwt.verify(token, process.env.JWT_VERIFY_KEY || 'margin_verify_secret');

    const user = await UserModel.findOne({ email: decoded.email, username: decoded.username });
    if (!user) {
      return res.json({ code: Code.Error, message: 'Invalid user' });
    }

    user.emailVerified = true;
    await user.save();

    return res.json({ code: Code.Success, data: { username: user.username } });
  } catch (err: any) {
    if (err.name === 'TokenExpiredError') {
      return res.json({ code: Code.Error, message: 'Verification link has expired' });
    }
    return res.json({ code: Code.Error, message: 'Invalid verification token' });
  }
});

export default router;
