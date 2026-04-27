// backend/src/api/routes/admin/humanize.ts
//
// Admin Humanize jobs — list / detail / cancel / delete. Built on the shared
// _jobUtils helper so the four job sections (humanize, plagiarism, autocite,
// documents) stay in lockstep.

import { Router } from 'express';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { registerJobSection } from './_jobUtils';

export default () => {
  const router = Router();
  registerJobSection(router, {
    path: '/humanize',
    model: HumanizeJobModel as any,
    searchFields: ['inputText', 'outputText', 'tone'],
    statuses: ['pending', 'processing', 'completed', 'done', 'failed', 'cancelled'],
    cancellable: true,
  });
  return router;
};
