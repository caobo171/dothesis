// frontend/app/admin/autocite/page.tsx

'use client';

import React from 'react';
import JobListPage, { renderStatus, JobBase } from '../_components/JobListPage';

type AutoCiteRow = JobBase & {
  style?: string;
  creditsUsed?: number;
  claims?: any[];
  sources?: any[];
};

export default function AdminAutoCitePage() {
  return (
    <JobListPage<AutoCiteRow>
      title="AutoCite jobs"
      url="/api/admin/autocite"
      detailHrefPrefix="/admin/autocite"
      searchPlaceholder="Search style"
      statuses={['pending', 'processing', 'completed', 'failed', 'cancelled']}
      extraColumns={[
        { key: 'status', header: 'Status', render: (r) => renderStatus(r.status) },
        { key: 'style', header: 'Style', render: (r) => r.style || '—' },
        { key: 'claims', header: 'Claims', render: (r) => r.claims?.length ?? 0 },
        { key: 'sources', header: 'Sources', render: (r) => r.sources?.length ?? 0 },
        { key: 'credits', header: 'Credits', render: (r) => <span className="font-mono">{r.creditsUsed ?? 0}</span> },
      ]}
    />
  );
}
