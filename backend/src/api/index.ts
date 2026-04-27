import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';
import document from './routes/document';
import humanize from './routes/humanize';
import cite from './routes/cite';
import library from './routes/library';
import plagiarism from './routes/plagiarism';
import webhook from './routes/webhook';
import announcementPublic from './routes/announcement.public';
import adminRouter from './routes/admin';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);
  document(router);
  humanize(router);
  cite(router);
  library(router);
  plagiarism(router);
  webhook(router);
  announcementPublic(router);

  // Admin sub-router. Each handler inside applies passport.authenticate + requireAdmin
  // (and requireSuperAdmin where applicable). Mounting here puts everything under /api/admin/*.
  router.use('/admin', adminRouter());

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
