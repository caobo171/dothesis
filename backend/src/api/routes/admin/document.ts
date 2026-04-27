// backend/src/api/routes/admin/document.ts
//
// Documents are not jobs in the queue sense — no status field, no cancel.
// We still use the shared helper for list/detail/delete so the table shape
// is consistent with the other sections.

import { Router } from 'express';
import { DocumentModel } from '@/models/Document';
import { registerJobSection } from './_jobUtils';

export default () => {
  const router = Router();
  registerJobSection(router, {
    path: '/documents',
    model: DocumentModel as any,
    searchFields: ['title', 'content'],
    cancellable: false,
  });
  return router;
};
