import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';
import document from './routes/document';
import humanize from './routes/humanize';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);
  document(router);
  humanize(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
