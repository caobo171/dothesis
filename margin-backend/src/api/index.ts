import { Router } from 'express';

export default () => {
  const router = Router();

  // Routes will be registered here as they are built
  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
