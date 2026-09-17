"use client";

import { useMemo, useState } from "react";
import { diff_match_patch, DIFF_DELETE, DIFF_EQUAL, DIFF_INSERT } from "diff-match-patch";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, ClockIcon, HandThumbDownIcon, HandThumbUpIcon, SparklesIcon } from "@heroicons/react/24/outline";

export type PendingEdit = {
  id: string;
  source: "paraphrase" | "translate" | "cite" | "chat_rewrite" | "proofread" | "improve" | "humanize" | "expand" | "shorten";
  oldText: string;
  newText: string;
  from_offset: number;
  to_offset: number;
  explanation?: string;
  processingMs?: number;
  metadata?: { target_lang?: string; reference_id?: string; style?: string; prompt?: string; document_fingerprint?: string };
};

type Props = {
  edit: PendingEdit;
  onAccept: (id: string, mode?: "replace" | "insert_after") => void;
  onReject: (id: string) => void;
  onRetry?: (edit: PendingEdit) => void;
  stale: boolean;
  busy?: boolean;
};

const _LABEL: Record<PendingEdit["source"], string> = {
  paraphrase: "Paraphrase", translate: "Translate", cite: "Cite", chat_rewrite: "Chat rewrite",
  proofread: "Proofread", improve: "Improve", humanize: "Humanize", expand: "Expand", shorten: "Shorten",
};
const _WHY: Record<PendingEdit["source"], string> = {
  paraphrase: "Diễn đạt lại để câu văn tự nhiên và học thuật hơn mà không đổi ý nghĩa.",
  translate: "Chuyển ngữ và giữ nguyên thuật ngữ chuyên môn, số liệu cùng trích dẫn.",
  cite: "Bổ sung trích dẫn đã được lưu trong thư viện nguồn của dự án.",
  chat_rewrite: "Điều chỉnh đoạn văn theo yêu cầu trong chat, chờ bạn duyệt trước khi ghi vào chương.",
  proofread: "Sửa ngữ pháp, chính tả, dấu câu và cách dùng từ chưa tự nhiên.",
  improve: "Tăng độ chính xác, mạch lạc và trang trọng của văn phong học thuật.",
  humanize: "Giảm lối diễn đạt máy móc và lặp cấu trúc để đoạn văn tự nhiên hơn.",
  expand: "Bổ sung giải thích và liên kết lập luận mà không tự tạo dữ liệu hay nguồn.",
  shorten: "Loại bỏ phần lặp và từ đệm, giữ lại toàn bộ nội dung có ý nghĩa.",
};

function InlineDiff({ oldText, newText }: { oldText: string; newText: string }) {
  const parts = useMemo(() => {
    const dmp = new diff_match_patch();
    const diff = dmp.diff_main(oldText, newText);
    dmp.diff_cleanupSemantic(diff);
    return diff;
  }, [oldText, newText]);
  return <div className="whitespace-pre-wrap text-[15px] leading-7 text-ink-900">{parts.map(([op, text], index) => {
    if (op === DIFF_DELETE) return <del key={index} className="bg-red-100 px-0.5 text-red-600 decoration-2">{text}</del>;
    if (op === DIFF_INSERT) return <ins key={index} className="bg-emerald-100 px-0.5 text-emerald-700 no-underline">{text}</ins>;
    if (op === DIFF_EQUAL) return <span key={index}>{text}</span>;
    return null;
  })}</div>;
}

export function PendingEditRibbon({ edit, onAccept, onReject, onRetry, stale, busy = false }: Props) {
  const [showDiff, setShowDiff] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  if (stale) return <div className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"><span><strong>Stale · {_LABEL[edit.source]}</strong> — nội dung gốc đã thay đổi nên đề xuất này không còn áp dụng an toàn.</span><button type="button" aria-label="Discard" disabled={busy} onClick={() => onReject(edit.id)} className="shrink-0 font-semibold hover:underline disabled:opacity-50">Discard</button></div>;
  const seconds = edit.processingMs ? Math.max(1, Math.round(edit.processingMs / 1000)) : null;
  return <article className="overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-[0_18px_55px_rgba(39,46,72,0.12)]">
    <header className="flex items-center gap-3 border-b border-ink-100 px-5 py-3.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-50 text-primary-600"><SparklesIcon className="h-[18px] w-[18px]" /></span>
      <div className="min-w-0 flex-1"><div className="text-sm font-semibold text-ink-900">{_LABEL[edit.source]}</div><div className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-400"><ClockIcon className="h-3.5 w-3.5" />{seconds ? `Đã xử lý trong ${seconds} giây` : "Đề xuất AI đang chờ duyệt"}</div></div>
      <button type="button" onClick={() => setShowDiff(v => !v)} className="rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-semibold text-ink-700 transition hover:bg-ink-50 active:translate-y-px">{showDiff ? "Hide edits" : "See edits"}</button>
      <button type="button" aria-label="Helpful" aria-pressed={feedback === "up"} onClick={() => setFeedback(feedback === "up" ? null : "up")} className={`rounded-lg p-2 transition hover:bg-ink-50 ${feedback === "up" ? "text-primary-600" : "text-ink-500"}`}><HandThumbUpIcon className="h-[18px] w-[18px]" /></button>
      <button type="button" aria-label="Not helpful" aria-pressed={feedback === "down"} onClick={() => setFeedback(feedback === "down" ? null : "down")} className={`rounded-lg p-2 transition hover:bg-ink-50 ${feedback === "down" ? "text-red-600" : "text-ink-500"}`}><HandThumbDownIcon className="h-[18px] w-[18px]" /></button>
    </header>
    <div className="px-5 py-4">{showDiff ? <InlineDiff oldText={edit.oldText} newText={edit.newText} /> : <p className="whitespace-pre-wrap text-[15px] leading-7 text-ink-900">{edit.newText}</p>}</div>
    <section className="border-y border-ink-100 bg-ink-50/60">
      <button type="button" aria-expanded={showWhy} onClick={() => setShowWhy(v => !v)} className="flex w-full items-center justify-between px-5 py-3.5 text-left text-sm font-semibold text-ink-800 transition hover:bg-ink-50"><span>What changed and why</span>{showWhy ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />}</button>
      {showWhy && <p className="border-t border-ink-100 px-5 py-4 text-sm leading-6 text-ink-600">{edit.explanation || _WHY[edit.source]}</p>}
    </section>
    <footer className="flex flex-wrap items-center gap-2 px-4 py-3">
      <button type="button" aria-label="Accept" disabled={busy} onClick={() => onAccept(edit.id)} className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-700 active:translate-y-px disabled:cursor-wait disabled:opacity-60"><CheckIcon className="h-4 w-4" />{busy ? "Working…" : "Replace selection"}</button>
      {edit.source !== "cite" && <button type="button" disabled={busy} onClick={() => onAccept(edit.id, "insert_after")} className="rounded-xl border border-ink-200 px-3.5 py-2 text-sm font-medium text-ink-700 transition hover:bg-ink-50 active:translate-y-px disabled:opacity-50">Insert below</button>}
      {onRetry && <button type="button" disabled={busy} onClick={() => onRetry(edit)} className="rounded-lg px-3 py-2 text-sm font-medium text-ink-600 transition hover:bg-ink-50 disabled:opacity-50">Try again</button>}
      <button type="button" aria-label="Reject" disabled={busy} onClick={() => onReject(edit.id)} className="ml-auto rounded-lg px-3 py-2 text-sm font-medium text-ink-500 transition hover:bg-red-50 hover:text-red-700 disabled:opacity-50">Discard</button>
    </footer>
  </article>;
}
