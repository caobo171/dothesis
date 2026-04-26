import { Router } from 'express';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';
import { Code, FREE_SIGNUP_CREDITS } from '@/Constants';
import jwt from 'jsonwebtoken';
import { v4 as uuidv4 } from 'uuid';

const router = Router();

router.post('/google', async (req, res) => {
  try {
    const { credential } = req.body;
    if (!credential) {
      return res.json({ code: Code.InvalidInput, message: 'Missing credential' });
    }

    // Decode the Google JWT (id_token) to get user info
    const payload = JSON.parse(
      Buffer.from(credential.split('.')[1], 'base64').toString()
    );

    const { sub: googleId, email, name } = payload;

    let user = await UserModel.findOne({
      $or: [{ googleId }, { email: email.toLowerCase() }],
    });

    if (!user) {
      user = await UserModel.create({
        username: email.split('@')[0],
        fullName: name || email.split('@')[0],
        email: email.toLowerCase(),
        password: Crypto.hashUsernamePassword(uuidv4()),
        googleId,
        emailVerified: true,
        credit: FREE_SIGNUP_CREDITS,
        plan: 'free',
        role: 'User',
      });
    } else if (!user.googleId) {
      user.googleId = googleId;
      user.emailVerified = true;
      await user.save();
    }

    const token = jwt.sign(
      { id: user._id, email: user.email, username: user.username },
      process.env.JWT_SECRET || 'margin_secret',
      { expiresIn: '7d' }
    );

    user.lastLogin = new Date();
    await user.save();

    return res.json({
      code: Code.Success,
      data: { token, user: user.secureRelease() },
    });
  } catch (err: any) {
    return res.json({ code: Code.Error, message: err.message });
  }
});

export default router;
