"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { X } from "lucide-react";
import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";


export function AutoDraftModal({
  open,
  projectId,
  defaultTopic,
  onClose,
  onConfirm,
}: {
  open: boolean;
  projectId: string;
  defaultTopic: string;
  onClose: () => void;
  onConfirm: (topic: string) => void;
}) {
  const [topic, setTopic] = useState(defaultTopic);
  // Sync topic when defaultTopic changes (e.g. project data arrives after modal mount)
  useEffect(() => {
    if (defaultTopic && !topic) setTopic(defaultTopic);
  }, [defaultTopic]);
  const { data: est } = useSWR(
    open && projectId ? `/projects/${projectId}/runs/estimate?topic=${encodeURIComponent(topic)}` : null,
    fetcher,
  );

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-ink-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink-900">Auto write full thesis</h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-ink-500" />
          </button>
        </div>

        <label className="block text-sm font-medium text-ink-700 mb-1">Research topic</label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          rows={3}
          className="w-full border border-ink-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 mb-4"
        />

        {est && (
          <div className="bg-ink-50 rounded-md p-3 text-sm mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-ink-600">Estimated tokens:</span>
              <span className="font-medium">{(est.estimated_tokens as number).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-600">Your balance:</span>
              <span className={`font-medium ${est.sufficient_credit ? "" : "text-red-600"}`}>
                {(est.credit_balance as number).toLocaleString()}
              </span>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-100 rounded-md"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(topic)}
            disabled={!topic.trim() || (est && !est.sufficient_credit)}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50"
          >
            Autopilot
          </button>
        </div>
      </div>
    </div>
  );
}
