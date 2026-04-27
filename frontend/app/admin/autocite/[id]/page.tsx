// frontend/app/admin/autocite/[id]/page.tsx

'use client';

import React from 'react';
import JobDetailFrame, { JobDetailBase } from '../../_components/JobDetailFrame';
import StatusBadge from '../../_components/StatusBadge';

type Claim = {
  text?: string;
  sourceId?: string;
  status?: string;
  candidates?: Array<{ sourceId: string; relevanceScore: number }>;
};

type Source = {
  id?: string;
  cite?: string;
  authorShort?: string;
  year?: number;
  title?: string;
  snippet?: string;
  conf?: number;
  sourceApi?: string;
};

type AutoCiteJob = JobDetailBase & {
  style?: string;
  creditsUsed?: number;
  claims?: Claim[];
  sources?: Source[];
  documentId?: string;
};

export default function AdminAutoCiteDetailPage() {
  return (
    <JobDetailFrame<AutoCiteJob>
      title="AutoCite job"
      detailUrl="/api/admin/autocite/get"
      cancelUrl="/api/admin/autocite/cancel"
      deleteUrl="/api/admin/autocite/delete"
      listHref="/admin/autocite"
      renderBody={(job) => (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Summary</div>
            <div className="grid grid-cols-4 gap-4 text-sm">
              <Stat k="Style" v={job.style || '—'} />
              <Stat k="Claims" v={job.claims?.length ?? 0} />
              <Stat k="Sources" v={job.sources?.length ?? 0} />
              <Stat k="Credits" v={job.creditsUsed ?? 0} />
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Claims</div>
            {(!job.claims || job.claims.length === 0) ? (
              <div className="text-sm text-gray-500">No claims.</div>
            ) : (
              <ul className="space-y-2">
                {job.claims.map((c, i) => (
                  <li key={i} className="rounded border border-gray-100 p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-gray-900">{c.text || '(empty)'}</div>
                      <StatusBadge tone={c.status === 'matched' ? 'green' : c.status === 'failed' ? 'red' : 'gray'}>
                        {c.status || 'pending'}
                      </StatusBadge>
                    </div>
                    {c.candidates && c.candidates.length > 0 && (
                      <div className="mt-2 text-xs text-gray-500">
                        {c.candidates.length} candidate(s) · top score{' '}
                        {Math.max(...c.candidates.map((x) => x.relevanceScore || 0)).toFixed(2)}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Sources</div>
            {(!job.sources || job.sources.length === 0) ? (
              <div className="text-sm text-gray-500">No sources.</div>
            ) : (
              <ul className="space-y-2">
                {job.sources.map((s, i) => (
                  <li key={i} className="rounded border border-gray-100 p-3 text-sm">
                    <div className="font-medium text-gray-900">
                      {s.authorShort || '?'} ({s.year || '?'}) — {s.title || 'Untitled'}
                    </div>
                    {s.cite && <div className="mt-1 font-mono text-xs text-gray-700">{s.cite}</div>}
                    {s.snippet && <div className="mt-1 text-xs text-gray-600">{s.snippet}</div>}
                    {s.sourceApi && <div className="mt-1 text-xs text-gray-400">via {s.sourceApi}</div>}
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

function Stat({ k, v }: { k: string; v: any }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-500">{k}</div>
      <div className="mt-1 text-xl font-semibold text-gray-900">{v}</div>
    </div>
  );
}
