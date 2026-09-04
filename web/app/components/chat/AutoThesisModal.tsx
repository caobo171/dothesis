"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { X } from "lucide-react";
import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";


export function AutoThesisModal({
  open,
  projectId,
  defaultTopic,
  derived = false,
  onClose,
  onConfirm,
}: {
  open: boolean;
  projectId: string;
  defaultTopic: string;
  /**
   * The topic was READ OUT of the student's uploads rather than typed by them
   * (POST /projects/{id}/topic-from-uploads).
   *
   * It changes what this dialog is for. Opened from the workspace button it is
   * a start-the-run gate, and the estimate is the useful part. Opened on a
   * derived topic it is showing the student a machine's guess about their own
   * thesis before six chapters get written on it — so the title is the whole
   * point and a token count next to it is noise at the moment they most need
   * to read one sentence carefully.
   */
  derived?: boolean;
  onClose: () => void;
  onConfirm: (topic: string) => void | Promise<unknown>;
}) {
  const t = useT();
  const [topic, setTopic] = useState(defaultTopic);
  const [starting, setStarting] = useState(false);
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
          <h2 className="text-lg font-semibold text-ink-900">
            {derived ? t("auto.derived.title") : "Auto Thesis"}
          </h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-ink-500" />
          </button>
        </div>

        <label className="block text-sm font-medium text-ink-700 mb-1">
          {derived ? t("auto.derived.topic") : "Research topic"}
        </label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          rows={3}
          className={"w-full border border-ink-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 " +
                     (derived ? "mb-1.5" : "mb-4")}
        />

        {/* Say the title is editable. The student did not write it, so nothing
            about a prefilled box tells them they are allowed to correct it. */}
        {derived && (
          <p className="text-[12.5px] text-ink-500 mb-4">{t("auto.derived.edit")}</p>
        )}

        {/* The estimate block is the workspace button's gate. On a derived
            topic it is replaced by the credit WARNING alone: the balance only
            matters here when it blocks the run, and the sentence above is what
            the student is supposed to be reading. */}
        {derived && est && !est.sufficient_credit && (
          <p className="text-sm text-red-600 mb-4">{t("auto.derived.lowCredit")}</p>
        )}

        {!derived && est && (
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
            onClick={() => {
              // Await the start so a second click can't spawn a second run,
              // and so the parent can keep this dialog open until POST
              // /runs actually succeeds (closing first is what dumped the
              // student onto an empty thread).
              setStarting(true);
              void Promise.resolve(onConfirm(topic)).finally(() => setStarting(false));
            }}
            disabled={!topic.trim() || starting || (est && !est.sufficient_credit)}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50"
          >
            {starting ? t("new.auto.analyzing") : derived ? t("auto.derived.start") : "Auto Thesis"}
          </button>
        </div>
      </div>
    </div>
  );
}
