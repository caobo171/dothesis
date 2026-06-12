"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { X } from "lucide-react";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


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
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Start auto-draft</h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <label className="block text-sm font-medium text-gray-700 mb-1">Research topic</label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          rows={3}
          className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 mb-4"
        />

        {est && (
          <div className="bg-gray-50 rounded-md p-3 text-sm mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-gray-600">Estimated tokens:</span>
              <span className="font-medium">{(est.estimated_tokens as number).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Your balance:</span>
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
            className="px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded-md"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(topic)}
            disabled={!topic.trim() || (est && !est.sufficient_credit)}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50"
          >
            Start auto-draft
          </button>
        </div>
      </div>
    </div>
  );
}
