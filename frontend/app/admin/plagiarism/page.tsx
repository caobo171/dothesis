// frontend/app/admin/plagiarism/page.tsx

'use client';

import React from 'react';
import JobListPage, { renderStatus, JobBase } from '../_components/JobListPage';

type PlagiarismRow = JobBase & {
  overallScore?: number;
  creditsUsed?: number;
  matches?: any[];
};

export default function AdminPlagiarismPage() {
  return (
    <JobListPage<PlagiarismRow>
      title="Plagiarism jobs"
      url="/api/admin/plagiarism"
      detailHrefPrefix="/admin/plagiarism"
      showSearch={false}
      statuses={['pending', 'processing', 'completed', 'failed', 'cancelled']}
      extraColumns={[
        { key: 'status', header: 'Status', render: (r) => renderStatus(r.status) },
        {
          key: 'score',
          header: 'Score',
          render: (r) => <span className="font-mono">{(r.overallScore ?? 0).toFixed(1)}%</span>,
        },
        { key: 'matches', header: 'Matches', render: (r) => r.matches?.length ?? 0 },
        { key: 'credits', header: 'Credits', render: (r) => <span className="font-mono">{r.creditsUsed ?? 0}</span> },
      ]}
    />
  );
}
