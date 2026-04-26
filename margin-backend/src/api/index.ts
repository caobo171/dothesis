import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';
import document from './routes/document';
import humanize from './routes/humanize';
import cite from './routes/cite';
import library from './routes/library';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);
  document(router);
  humanize(router);
  cite(router);
  library(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
