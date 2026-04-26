import { Router } from 'express';
import signup from './signup';
import signin from './signin';
import google from './google';
import verify from './verify';
import resendEmail from './resend.email';

export default (router: Router) => {
  router.use('/auth', signup);
  router.use('/auth', signin);
  router.use('/auth', google);
  router.use('/auth', verify);
  router.use('/auth', resendEmail);
};
