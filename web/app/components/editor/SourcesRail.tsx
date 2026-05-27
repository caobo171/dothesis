"use client";

import useSWR from "swr";


type Reference = { id: string; author: string; year: string; title?: string };


const fetcher = (url: string) => fetch(url).then(r => r.json());


// Right rail. Read-only browser of the M2 reference pool. Insertion happens
// via the SelectionToolbar's Cite popover; this rail is for "what's available"
// at-a-glance.
export function SourcesRail({ projectId }: { projectId: string }) {
  const { data } = useSWR<Reference[]>(`/api/v1/projects/${projectId}/m5/references`, fetcher);
  const refs = data ?? [];
  return (
    <aside className="w-56 shrink-0 border-l border-gray-200 py-4 px-3 overflow-y-auto">
      <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
        Sources ({refs.length})
      </div>
      {refs.length === 0 ? (
        <div className="text-xs text-gray-500">No references yet.</div>
      ) : (
        <ul className="space-y-1">
          {refs.map(r => (
            <li key={r.id} className="text-xs text-gray-700 bg-gray-50 rounded px-2 py-1">
              <div className="font-medium text-gray-900">{r.author} ({r.year})</div>
              {r.title && <div className="text-gray-500 truncate">{r.title}</div>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
