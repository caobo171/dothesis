"use client";

import { useEffect, useState } from "react";
import { ArrowLeftIcon } from "@heroicons/react/24/outline";

import { apiFetch } from "@/app/lib/api";


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
    // POST-only read: apiFetch folds access_token into the JSON body so the
    // token never appears in the URL.
    apiFetch(`/projects/${projectId}/m5/references`, { method: "POST" })
      .then((data: any) => { if (!cancelled) setRefs(data); })
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

  // Escape returns to the selection toolbar. Without a way back, opening Cite
  // over an empty reference list was a dead end — nothing to select, no button
  // to close, so the only escape was clicking away and losing the selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div role="dialog" aria-label="Insert citation"
         className="bg-white border border-primary-500 rounded-md shadow-lg p-2 w-64 z-50">
      {/* Back to the selection toolbar. */}
      <button
        type="button"
        onClick={onClose}
        className="inline-flex items-center gap-1 text-[12px] font-medium text-ink-500 hover:text-ink-900 mb-2 px-1 py-0.5 rounded hover:bg-ink-50"
      >
        <ArrowLeftIcon className="w-3.5 h-3.5" /> Back
      </button>
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
          <a href={`/chat/projects/${projectId}`} className="text-primary-600 underline">Open chat</a>
        </div>
      )}
      {refs !== null && refs.length > 0 && (
        <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5">
          {filtered.map(r => (
            <button
              key={r.id}
              type="button"
              onClick={() => { onSelect(r.id); onClose(); }}
              className="text-left text-xs px-2 py-1.5 hover:bg-primary-50 rounded"
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
