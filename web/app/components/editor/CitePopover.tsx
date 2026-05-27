"use client";

import { useEffect, useState } from "react";


type Reference = { id: string; author: string; year: string; title?: string };


type Props = {
  projectId: string;
  onSelect: (referenceId: string) => void;
  onClose: () => void;
};


export function CitePopover({ projectId, onSelect, onClose }: Props) {
  const [refs, setRefs] = useState<Reference[] | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/projects/${projectId}/m5/references`)
      .then(r => r.json())
      .then(data => { if (!cancelled) setRefs(data); })
      .catch(() => { if (!cancelled) setRefs([]); });
    return () => { cancelled = true; };
  }, [projectId]);

  const filtered = (refs ?? []).filter(r => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      r.author?.toLowerCase().includes(q) ||
      r.year?.toString().includes(q) ||
      r.title?.toLowerCase().includes(q)
    );
  });

  return (
    <div role="dialog" aria-label="Insert citation"
         className="bg-white border border-purple-300 rounded-md shadow-lg p-2 w-64 z-50">
      <input
        type="text"
        autoFocus
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search references…"
        className="w-full text-sm px-2 py-1 border border-gray-200 rounded mb-2"
      />
      {refs === null && <div className="text-xs text-gray-400 px-2 py-1">Loading…</div>}
      {refs !== null && refs.length === 0 && (
        <div className="text-xs text-gray-500 px-2 py-2">
          No references yet. Citations are added in M2.{" "}
          <a href={`/chat/projects/${projectId}`} className="text-purple-600 underline">Open chat</a>
        </div>
      )}
      {refs !== null && refs.length > 0 && (
        <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5">
          {filtered.map(r => (
            <button
              key={r.id}
              type="button"
              onClick={() => { onSelect(r.id); onClose(); }}
              className="text-left text-xs px-2 py-1.5 hover:bg-purple-50 rounded"
            >
              <div className="font-medium text-gray-900">{r.author} ({r.year})</div>
              {r.title && <div className="text-gray-500 truncate">{r.title}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
