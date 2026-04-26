import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';

export default () => {
  const router = Router();

  auth(router);
  me(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
