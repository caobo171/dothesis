// frontend/app/admin/humanize/[id]/page.tsx

'use client';

import React from 'react';
import JobDetailFrame, { JobDetailBase } from '../../_components/JobDetailFrame';

type HumanizeJob = JobDetailBase & {
  tone?: string;
  strength?: number;
  lengthMode?: string;
  iterations?: number;
  creditsUsed?: number;
  aiScoreIn?: number;
  aiScoreOut?: number;
  changesCount?: number;
  inputText?: string;
  outputText?: string;
  outputHtml?: string;
  tokenUsage?: {
    steps: Array<{ step: string; model: string; iteration: number; inputTokens: number; outputTokens: number }>;
    totalInputTokens: number;
    totalOutputTokens: number;
  };
};

export default function AdminHumanizeDetailPage() {
  return (
    <JobDetailFrame<HumanizeJob>
      title="Humanize job"
      detailUrl="/api/admin/humanize/get"
      cancelUrl="/api/admin/humanize/cancel"
      deleteUrl="/api/admin/humanize/delete"
      listHref="/admin/humanize"
      renderBody={(job) => (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Settings</div>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Cell k="Tone" v={job.tone} />
              <Cell k="Strength" v={job.strength} />
              <Cell k="Length mode" v={job.lengthMode} />
              <Cell k="Iterations" v={job.iterations} />
              <Cell k="Credits used" v={job.creditsUsed} />
              <Cell k="Changes" v={job.changesCount} />
              <Cell k="AI score in" v={job.aiScoreIn} />
              <Cell k="AI score out" v={job.aiScoreOut} />
            </dl>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Token usage</div>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Cell k="Total input tokens" v={job.tokenUsage?.totalInputTokens} />
              <Cell k="Total output tokens" v={job.tokenUsage?.totalOutputTokens} />
            </dl>
            {job.tokenUsage?.steps && job.tokenUsage.steps.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 text-xs uppercase tracking-wider text-gray-500">Steps</div>
                <div className="overflow-x-auto rounded border border-gray-200">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 text-gray-600">
                      <tr>
                        <th className="px-2 py-1 text-left">Step</th>
                        <th className="px-2 py-1 text-left">Model</th>
                        <th className="px-2 py-1 text-right">Iter</th>
                        <th className="px-2 py-1 text-right">In</th>
                        <th className="px-2 py-1 text-right">Out</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.tokenUsage.steps.map((s, i) => (
                        <tr key={i} className="border-t border-gray-100">
                          <td className="px-2 py-1">{s.step}</td>
                          <td className="px-2 py-1 font-mono text-[11px]">{s.model}</td>
                          <td className="px-2 py-1 text-right">{s.iteration}</td>
                          <td className="px-2 py-1 text-right">{s.inputTokens}</td>
                          <td className="px-2 py-1 text-right">{s.outputTokens}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 lg:col-span-2">
            <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Input</div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-800">
              {job.inputText || ''}
            </pre>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 lg:col-span-2">
            <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Output (text)</div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-800">
              {job.outputText || ''}
            </pre>
          </div>
        </div>
      )}
    />
  );
}

function Cell({ k, v }: { k: string; v: any }) {
  return (
    <div className="contents">
      <dt className="text-xs uppercase tracking-wider text-gray-500">{k}</dt>
      <dd className="text-right text-gray-900">{v ?? '—'}</dd>
    </div>
  );
}
