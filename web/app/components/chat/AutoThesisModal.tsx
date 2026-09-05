"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import useSWR from "swr";
import { X, Loader2 } from "lucide-react";
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
   * thesis before five chapters get written on it — so the title is the whole
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
  // This dialog read the topic out of the uploads itself, as opposed to being
  // handed one already derived by the caller. Same framing either way.
  const [readFromFiles, setReadFromFiles] = useState(false);
  const [reading, setReading] = useState(false);
  const askedFor = useRef<string | null>(null);
  // Sync topic when defaultTopic changes (e.g. project data arrives after modal mount)
  useEffect(() => {
    if (defaultTopic && !topic) setTopic(defaultTopic);
  }, [defaultTopic]);

  // Nothing to start a run on, and the title is very likely sitting on page 1
  // of a file the student already uploaded. Read it.
  //
  // This lives HERE rather than in the caller because ChatPane opens this
  // dialog from four places and only one of them derived a topic: the auto-mode
  // empty-thread prompt, the workspace button and both start-failure fallbacks
  // all opened it blank, so a student who had uploaded a finished results
  // chapter was asked to retype the title they had just handed over. Three
  // surfaces cannot each remember to do this. The dialog that needs the topic
  // is the thing that asks for it.
  //
  // Cheap where it should be: POST /topic-from-uploads returns without an LLM
  // call when a title is already committed or the project has no readable
  // files, so only the case this exists for costs anything.
  useEffect(() => {
    if (!open || !projectId) return;
    if (defaultTopic || topic) return;             // already have one
    if (askedFor.current === projectId) return;    // once per project, not per render
    askedFor.current = projectId;
    setReading(true);
    void apiFetch(`/projects/${projectId}/topic-from-uploads`, { method: "POST", body: {} })
      .then(res => {
        const title = ((res as { research_title?: string | null })?.research_title || "").trim();
        if (title) {
          setTopic(title);
          setReadFromFiles(true);
        }
      })
      // No files, nothing readable, or the read failed: all three land on the
      // same fallback, which is the empty box asking the student to type it.
      .catch(() => {})
      .finally(() => setReading(false));
  }, [open, projectId, defaultTopic, topic]);

  const isDerived = derived || readFromFiles;
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
            {isDerived ? t("auto.derived.title") : "Auto Thesis"}
          </h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-ink-500" />
          </button>
        </div>

        <label className="block text-sm font-medium text-ink-700 mb-1">
          {isDerived ? t("auto.derived.topic") : "Research topic"}
        </label>

        {/* Reading the files is one LLM call, seconds not instant. Unlabelled,
            an empty box that fills itself a moment later reads as a glitch. */}
        {reading && (
          <p className="mb-1.5 inline-flex items-center gap-1.5 text-[12.5px] text-ink-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
            {t("auto.derived.reading")}
          </p>
        )}
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          rows={3}
          className={"w-full border border-ink-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 " +
                     (isDerived ? "mb-1.5" : "mb-4")}
        />

        {/* Say the title is editable. The student did not write it, so nothing
            about a prefilled box tells them they are allowed to correct it. */}
        {isDerived && (
          <p className="text-[12.5px] text-ink-500 mb-4">{t("auto.derived.edit")}</p>
        )}

        {/* The estimate block is the workspace button's gate. On a derived
            topic the numbers are suppressed: the student is being shown a
            machine's guess at their own title, and a token count next to it is
            noise at the moment they most need to read one sentence carefully. */}
        {!isDerived && est && (
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

        {/* The warning belongs on BOTH paths, not just the derived one. Without
            it the typed-topic dialog rendered a red number and a dead button and
            said nothing: the student can see their balance is short but not that
            it is what blocks the run, nor what to do about it. A disabled button
            with no sentence next to it is a dead end, so this names the shortfall
            and links to the one page that fixes it. */}
        {est && !est.sufficient_credit && (
          <div className="text-sm text-red-600 mb-4">
            <p>{t("auto.derived.lowCredit")}</p>
            <p className="mt-0.5">
              {t("auto.lowCredit.short", {
                count: Math.max(
                  0,
                  (est.estimated_tokens as number) - (est.credit_balance as number),
                ).toLocaleString(),
              })}{" "}
              <Link href="/credit" className="underline font-medium hover:no-underline">
                {t("auto.lowCredit.action")}
              </Link>
            </p>
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
            disabled={!topic.trim() || starting || reading || (est && !est.sufficient_credit)}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-full hover:bg-primary-700 disabled:opacity-50"
          >
            {starting ? t("new.auto.analyzing") : isDerived ? t("auto.derived.start") : "Auto Thesis"}
          </button>
        </div>
      </div>
    </div>
  );
}
