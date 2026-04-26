'use client';

import { Claim, CiteSource } from '@/store/types';
import { clsx } from 'clsx';

interface ClaimPopoverProps {
  claim: Claim;
  claimIndex: number;
  sources: CiteSource[];
  onAccept: (claimIndex: number, sourceId: string) => void;
  onRemove: (claimIndex: number) => void;
}

export function ClaimPopover({ claim, claimIndex, sources, onAccept, onRemove }: ClaimPopoverProps) {
  const citedSource = claim.sourceId ? sources.find((s) => s.id === claim.sourceId) : null;
  const candidates = claim.candidates
    .map((c) => ({ ...c, source: sources.find((s) => s.id === c.sourceId) }))
    .filter((c) => c.source);

  if (citedSource) {
    return (
      <div className="p-3 bg-bg-blue rounded-lg border border-primary/20">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-primary">{citedSource.authorShort} ({citedSource.year})</p>
            <p className="text-xs text-ink-soft mt-0.5 truncate">{citedSource.title}</p>
          </div>
          <button
            onClick={() => onRemove(claimIndex)}
            className="text-xs text-error hover:underline shrink-0"
          >
            Remove
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-3 bg-white rounded-lg border border-rule">
      <p className="text-xs text-ink-muted mb-2">Suggested sources:</p>
      <div className="space-y-2">
        {candidates.length === 0 && (
          <p className="text-xs text-ink-muted italic">No candidates found</p>
        )}
        {candidates.map((c) => (
          <button
            key={c.sourceId}
            onClick={() => onAccept(claimIndex, c.sourceId)}
            className="w-full text-left p-2 rounded-md hover:bg-bg-soft transition border border-rule"
          >
            <p className="text-xs font-medium text-ink">{c.source!.authorShort} ({c.source!.year})</p>
            <p className="text-xs text-ink-muted truncate">{c.source!.title}</p>
            <div className="flex items-center gap-1 mt-1">
              <div className="w-12 h-1 bg-rule rounded-full overflow-hidden">
                <div
                  className="h-full bg-success rounded-full"
                  style={{ width: `${(c.relevanceScore || 0) * 100}%` }}
                />
              </div>
              <span className="text-[10px] text-ink-muted">
                {Math.round((c.relevanceScore || 0) * 100)}%
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
