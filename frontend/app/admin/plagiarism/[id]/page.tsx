// frontend/app/admin/plagiarism/[id]/page.tsx

'use client';

import React from 'react';
import JobDetailFrame, { JobDetailBase } from '../../_components/JobDetailFrame';
import StatusBadge from '../../_components/StatusBadge';

type PlagiarismMatch = {
  sourceTitle?: string;
  sourceUrl?: string;
  similarity?: number;
  matchedText?: string;
  severity?: string;
};

type PlagiarismJob = JobDetailBase & {
  overallScore?: number;
  creditsUsed?: number;
  matches?: PlagiarismMatch[];
  documentId?: string;
};

export default function AdminPlagiarismDetailPage() {
  return (
    <JobDetailFrame<PlagiarismJob>
      title="Plagiarism job"
      detailUrl="/api/admin/plagiarism/get"
      cancelUrl="/api/admin/plagiarism/cancel"
      deleteUrl="/api/admin/plagiarism/delete"
      listHref="/admin/plagiarism"
      renderBody={(job) => (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Summary</div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wider text-gray-500">Overall score</div>
                <div className="mt-1 text-xl font-semibold">{(job.overallScore ?? 0).toFixed(1)}%</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-gray-500">Matches</div>
                <div className="mt-1 text-xl font-semibold">{job.matches?.length ?? 0}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-gray-500">Credits used</div>
                <div className="mt-1 text-xl font-semibold">{job.creditsUsed ?? 0}</div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Matches</div>
            {(!job.matches || job.matches.length === 0) ? (
              <div className="text-sm text-gray-500">No matches recorded.</div>
            ) : (
              <ul className="space-y-3">
                {job.matches.map((m, i) => (
                  <li key={i} className="rounded border border-gray-100 p-3">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <div className="font-medium text-gray-900">{m.sourceTitle || 'Untitled source'}</div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs">{(m.similarity ?? 0).toFixed(1)}%</span>
                        {m.severity && <StatusBadge tone={m.severity === 'high' ? 'red' : m.severity === 'medium' ? 'yellow' : 'gray'}>{m.severity}</StatusBadge>}
                      </div>
                    </div>
                    {m.sourceUrl && (
                      <a href={m.sourceUrl} target="_blank" rel="noreferrer" className="mt-1 block text-xs text-blue-600 hover:underline">
                        {m.sourceUrl}
                      </a>
                    )}
                    {m.matchedText && (
                      <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-700">
                        {m.matchedText}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    />
  );
}
