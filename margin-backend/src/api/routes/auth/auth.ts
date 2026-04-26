import { Router } from 'express';
import signup from './signup';
import signin from './signin';
import google from './google';

export default (router: Router) => {
  router.use('/auth', signup);
  router.use('/auth', signin);
  router.use('/auth', google);
};
