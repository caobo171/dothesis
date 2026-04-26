'use client';

import { RawCitation } from '@/store/types';
import Fetch from '@/lib/core/fetch/Fetch';
import { toast } from 'react-toastify';

interface CitationRowProps {
  citation: RawCitation;
  onDeleted: () => void;
}

export function CitationRow({ citation, onDeleted }: CitationRowProps) {
  const handleDelete = async () => {
    await Fetch.postWithAccessToken('/api/library/citations/delete', { id: citation._id });
    onDeleted();
    toast.success('Citation deleted');
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(citation.formattedText);
    toast.success('Copied to clipboard');
  };

  return (
    <div className="px-4 py-3 hover:bg-bg-soft transition group">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-ink leading-relaxed">{citation.formattedText}</p>
          <div className="flex items-center gap-3 mt-1.5">
            <span className="text-[10px] text-ink-muted uppercase font-medium">{citation.style}</span>
            {citation.doi && (
              <span className="text-[10px] text-ink-muted">DOI: {citation.doi}</span>
            )}
          </div>
        </div>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
          <button onClick={handleCopy} className="text-xs text-primary hover:underline">
            Copy
          </button>
          <button onClick={handleDelete} className="text-xs text-error hover:underline">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
