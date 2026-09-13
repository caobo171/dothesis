"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, ScrollText } from "lucide-react";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { ContextSummaryHint } from "./types";

/**
 * The auto-compaction summary, labelled as one.
 *
 * When a thread crosses the compaction threshold, LangChain's
 * SummarizationMiddleware rewrites the history into a "## SESSION INTENT /
 * ## SUMMARY" note — through the SAME model, so its tokens used to stream out
 * on the reply channel and get persisted as the assistant's answer. A student
 * who asked to merge the construct cells in a table got back the agent's
 * private notes on their own thesis instead (M1: done, M2: done, [NEXT]…).
 *
 * `agent/runtime.py` now keeps that text out of the reply and sends it here.
 * Collapsed by default because it is not the answer; readable on demand
 * because it is not nothing either — compaction spends the student's credits
 * and decides what the agent still remembers about their thesis, and a summary
 * that got a fact wrong is something they can only catch by looking.
 */
export function ContextSummaryCard({ hint }: { hint: ContextSummaryHint }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const text = (hint.text || "").trim();
  if (!text) return null;

  return (
    <div
      className="mt-3 rounded-xl border border-ink-200 bg-ink-50/60 overflow-hidden"
      data-testid="context-summary-card"
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-[12.5px] text-ink-600 hover:bg-ink-100/60"
      >
        {open
          ? <ChevronDown className="w-3.5 h-3.5 shrink-0 text-ink-400" />
          : <ChevronRight className="w-3.5 h-3.5 shrink-0 text-ink-400" />}
        <ScrollText className="w-3.5 h-3.5 shrink-0 text-ink-400" />
        <span className="font-medium">{t("chat.contextSummary.title")}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-ink-200">
          <p className="text-[11.5px] text-ink-500 mb-2">
            {t("chat.contextSummary.hint")}
          </p>
          {/* Pre, not markdown: this is the agent's internal note verbatim.
              Rendering it as prose would dress it up as more of an answer than
              it is, and the reason to show it at all is to let a student check
              it against what they know. */}
          <pre className="text-[12px] leading-relaxed text-ink-700 whitespace-pre-wrap break-words max-h-80 overflow-y-auto font-sans">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}
