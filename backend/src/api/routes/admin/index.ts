// backend/src/api/routes/admin/index.ts
//
// Mount point for all admin section routers. Every section will be added here
// in subsequent slices (users, jobs, credits, announcements, ai-providers).
//
// The healthcheck route below proves the gating chain works end-to-end:
// passport (auth) -> requireAdmin -> handler.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { requireAdmin } from '@/api/middlewares/requireAdmin';
import userRouter from './user';
import creditRouter from './credit';
import humanizeRouter from './humanize';
import plagiarismRouter from './plagiarism';
import autociteRouter from './autocite';
import documentRouter from './document';
import announcementRouter from './announcement';

export default () => {
  const router = Router();

  // Each section sub-router applies its own auth + requireAdmin per route.
  router.use(userRouter());
  router.use(creditRouter());
  router.use(humanizeRouter());
  router.use(plagiarismRouter());
  router.use(autociteRouter());
  router.use(documentRouter());
  router.use(announcementRouter());

  router.post(
    '/healthcheck',
    passport.authenticate('jwt', { session: false }),
    requireAdmin,
    (req, res) => {
      const user = req.user as any;
      const released = user.secureRelease();
      return res.json({
        code: Code.Success,
        data: {
          ok: true,
          email: released.email,
          is_super_admin: released.is_super_admin,
        },
      });
    }
  );

  return router;
};
