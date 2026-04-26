'use client';

import { CiteSource, Claim } from '@/store/types';

interface SourceListProps {
  sources: CiteSource[];
  claims: Claim[];
}

export function SourceList({ sources, claims }: SourceListProps) {
  const citedSourceIds = claims.filter((c) => c.status === 'cited').map((c) => c.sourceId);
  const citedSources = sources.filter((s) => citedSourceIds.includes(s.id));

  if (citedSources.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-ink-muted">
        Accept sources from claims to build your bibliography
      </div>
    );
  }

  return (
    <div className="divide-y divide-rule">
      <div className="px-4 py-3 bg-bg-soft">
        <h3 className="text-xs font-semibold text-ink-soft">
          Bibliography ({citedSources.length} source{citedSources.length !== 1 ? 's' : ''})
        </h3>
      </div>
      {citedSources.map((source, i) => (
        <div key={source.id} className="px-4 py-3 hover:bg-bg-soft transition">
          <p className="text-xs text-ink-muted mb-0.5">[{i + 1}]</p>
          <p className="text-sm text-ink leading-relaxed">{source.cite || `${source.authorShort} (${source.year}). ${source.title}`}</p>
        </div>
      ))}
    </div>
  );
}
