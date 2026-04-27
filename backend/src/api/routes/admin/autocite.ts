// backend/src/api/routes/admin/autocite.ts

import { Router } from 'express';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { registerJobSection } from './_jobUtils';

export default () => {
  const router = Router();
  registerJobSection(router, {
    path: '/autocite',
    model: AutoCiteJobModel as any,
    searchFields: ['style'],
    statuses: ['pending', 'processing', 'completed', 'failed', 'cancelled'],
    cancellable: true,
  });
  return router;
};
