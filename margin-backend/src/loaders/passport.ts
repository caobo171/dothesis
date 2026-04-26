import { Application } from 'express';
import passport from 'passport';
import { Strategy as LocalStrategy } from 'passport-local';
import { Strategy as JwtStrategy, ExtractJwt } from 'passport-jwt';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';

export default ({ app }: { app: Application }) => {
  app.use(passport.initialize());
  app.use(passport.session());

  // Local Strategy for signin
  passport.use(
    'signin',
    new LocalStrategy(
      { usernameField: 'email', passwordField: 'password' },
      async (email, password, done) => {
        try {
          const user = await UserModel.findOne({
            $or: [{ email: email.toLowerCase() }, { username: email }],
          });
          if (!user) return done(null, false, { message: 'User not found' });
          if (!Crypto.checkCorrectPassword(password, user.password)) {
            return done(null, false, { message: 'Incorrect password' });
          }
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );

  // JWT Strategy
  passport.use(
    new JwtStrategy(
      {
        jwtFromRequest: (req) => {
          return req.body?.access_token || req.query?.access_token || null;
        },
        secretOrKey: process.env.JWT_SECRET || 'margin_secret',
      },
      async (payload, done) => {
        try {
          const user = await UserModel.findById(payload.id);
          if (!user) return done(null, false);
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );
};
