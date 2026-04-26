'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { FolderSidebar } from '@/components/library/FolderSidebar';
import { CitationRow } from '@/components/library/CitationRow';
import { useCitations } from '@/hooks/library';

export default function LibraryPage() {
  const { selectedFolderId } = useSelector((s: RootState) => s.library);
  const { citations, mutate } = useCitations(selectedFolderId);

  return (
    <div className="flex bg-white rounded-xl border border-rule overflow-hidden" style={{ minHeight: 500 }}>
      <FolderSidebar />
      <div className="flex-1 divide-y divide-rule">
        {citations.length === 0 ? (
          <div className="p-6 text-center text-sm text-ink-muted">
            No citations yet. Save citations from Auto-Cite to see them here.
          </div>
        ) : (
          citations.map((c: any) => (
            <CitationRow key={c._id} citation={c} onDeleted={() => mutate()} />
          ))
        )}
      </div>
    </div>
  );
}
