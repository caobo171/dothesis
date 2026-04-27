// frontend/app/admin/documents/[id]/page.tsx

'use client';

import React from 'react';
import JobDetailFrame, { JobDetailBase } from '../../_components/JobDetailFrame';

type Document = JobDetailBase & {
  title?: string;
  content?: string;
  sourceType?: string;
  sourceUrl?: string;
  fileKey?: string;
  mimeType?: string;
  wordCount?: number;
};

export default function AdminDocumentDetailPage() {
  return (
    <JobDetailFrame<Document>
      // Documents are not jobs — no cancel button. Delete is still available.
      title="Document"
      detailUrl="/api/admin/documents/get"
      deleteUrl="/api/admin/documents/delete"
      listHref="/admin/documents"
      renderBody={(doc) => (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-3 text-xs uppercase tracking-wider text-gray-500">Metadata</div>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Cell k="Title" v={doc.title} />
              <Cell k="Source type" v={doc.sourceType} />
              <Cell k="Mime" v={doc.mimeType} />
              <Cell k="Word count" v={doc.wordCount} />
              {doc.sourceUrl && <Cell k="URL" v={<a href={doc.sourceUrl} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">{doc.sourceUrl}</a>} />}
              {doc.fileKey && <Cell k="File key" v={<span className="font-mono text-xs">{doc.fileKey}</span>} />}
            </dl>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Content</div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-800">
              {doc.content || ''}
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
