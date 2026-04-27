// backend/src/api/routes/admin/plagiarism.ts

import { Router } from 'express';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { registerJobSection } from './_jobUtils';

export default () => {
  const router = Router();
  registerJobSection(router, {
    path: '/plagiarism',
    model: PlagiarismJobModel as any,
    searchFields: [],
    statuses: ['pending', 'processing', 'completed', 'failed', 'cancelled'],
    cancellable: true,
  });
  return router;
};
