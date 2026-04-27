// frontend/app/admin/humanize/page.tsx

'use client';

import React from 'react';
import JobListPage, { renderStatus, JobBase } from '../_components/JobListPage';

type HumanizeRow = JobBase & {
  tone?: string;
  strength?: number;
  iterations?: number;
  creditsUsed?: number;
  aiScoreIn?: number;
  aiScoreOut?: number;
  inputText?: string;
};

export default function AdminHumanizePage() {
  return (
    <JobListPage<HumanizeRow>
      title="Humanize jobs"
      url="/api/admin/humanize"
      detailHrefPrefix="/admin/humanize"
      searchPlaceholder="Search input/output/tone"
      statuses={['pending', 'processing', 'completed', 'done', 'failed', 'cancelled']}
      extraColumns={[
        { key: 'status', header: 'Status', render: (r) => renderStatus(r.status) },
        { key: 'tone', header: 'Tone', render: (r) => r.tone || '—' },
        { key: 'iter', header: 'Iter', render: (r) => r.iterations ?? 0 },
        {
          key: 'aiScore',
          header: 'AI score',
          render: (r) => (
            <span className="text-xs text-gray-600">
              {r.aiScoreIn ?? 0} → {r.aiScoreOut ?? 0}
            </span>
          ),
        },
        { key: 'credits', header: 'Credits', render: (r) => <span className="font-mono">{r.creditsUsed ?? 0}</span> },
      ]}
    />
  );
}
