import { Router } from 'express';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';
import { Valid } from '@/packages/valid/valid';
import { Mailer } from '@/packages/mail/mail';
import { Code, FREE_SIGNUP_CREDITS } from '@/Constants';
import jwt from 'jsonwebtoken';

const router = Router();

router.post('/signup', async (req, res) => {
  try {
    const { username, fullName, email, password, confirmPassword } = req.body;

    if (!Valid.string(username)) {
      return res.json({ code: Code.InvalidInput, message: 'Username is required' });
    }
    if (!Valid.username(username)) {
      return res.json({ code: Code.InvalidInput, message: 'Username can only contain letters, numbers, underscores and spaces' });
    }
    if (!Valid.string(fullName)) {
      return res.json({ code: Code.InvalidInput, message: 'Full name is required' });
    }
    if (!Valid.email(email)) {
      return res.json({ code: Code.InvalidInput, message: 'Invalid email' });
    }
    if (!password || password.length < 6) {
      return res.json({ code: Code.InvalidInput, message: 'Password must be at least 6 characters' });
    }
    if (password !== confirmPassword) {
      return res.json({ code: Code.InvalidInput, message: 'Passwords do not match' });
    }

    const existingEmail = await UserModel.findOne({ email: email.toLowerCase() });
    if (existingEmail) {
      return res.json({ code: Code.InvalidInput, message: 'Email already exists' });
    }

    const existingUsername = await UserModel.findOne({ username });
    if (existingUsername) {
      return res.json({ code: Code.InvalidInput, message: 'Username already taken' });
    }

    const hashedPassword = Crypto.hashUsernamePassword(password);

    const user = await UserModel.create({
      username,
      fullName,
      email: email.toLowerCase(),
      password: hashedPassword,
      credit: FREE_SIGNUP_CREDITS,
      emailVerified: false,
      plan: 'free',
      role: 'User',
    });

    // Send verification email
    const verifyToken = jwt.sign(
      { email: user.email, username: user.username },
      process.env.JWT_VERIFY_KEY || 'margin_verify_secret',
      { expiresIn: '24h' }
    );

    await Mailer.sendVerificationEmail(user.email, user.username, verifyToken);

    return res.json({
      code: Code.Success,
      message: 'Registration successful. Please check your email to verify your account.',
    });
  } catch (err: any) {
    return res.json({ code: Code.Error, message: err.message });
  }
});

export default router;
