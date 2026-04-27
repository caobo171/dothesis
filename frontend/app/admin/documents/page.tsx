// frontend/app/admin/documents/page.tsx

'use client';

import React from 'react';
import JobListPage, { JobBase } from '../_components/JobListPage';

type DocRow = JobBase & {
  title?: string;
  sourceType?: string;
  mimeType?: string;
  wordCount?: number;
};

export default function AdminDocumentsPage() {
  return (
    <JobListPage<DocRow>
      title="Documents"
      url="/api/admin/documents"
      detailHrefPrefix="/admin/documents"
      searchPlaceholder="Search title/content"
      // Documents have no status field — pass empty so filter dropdown is hidden.
      statuses={[]}
      extraColumns={[
        { key: 'title', header: 'Title', render: (r) => <span className="font-medium text-gray-900">{r.title || '(untitled)'}</span> },
        { key: 'source', header: 'Source', render: (r) => r.sourceType || '—' },
        { key: 'mime', header: 'Mime', render: (r) => <span className="font-mono text-xs">{r.mimeType || '—'}</span> },
        { key: 'words', header: 'Words', render: (r) => <span className="font-mono">{r.wordCount ?? 0}</span> },
      ]}
    />
  );
}
