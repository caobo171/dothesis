"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  SparklesIcon,
  ChevronDownIcon,
  ArrowPathIcon,
  ArrowTrendingUpIcon,
  CheckCircleIcon,
  UserIcon,
  ArrowsPointingOutIcon,
  ScissorsIcon,
  LanguageIcon,
  PaperClipIcon,
} from "@heroicons/react/24/outline";


type Props = {
  onRewrite: (kind: RewriteKind, prompt: string) => void;
  onTranslate: () => void;
  onCite: () => void;
};

export type RewriteKind = "paraphrase" | "improve" | "proofread" | "humanize" | "expand" | "shorten";

const PRESETS: Array<{ kind: RewriteKind; label: string; prompt: string; Icon: typeof SparklesIcon }> = [
  { kind: "paraphrase", label: "Paraphrase", prompt: "Diễn đạt lại đoạn này tự nhiên và học thuật hơn, giữ nguyên ý nghĩa.", Icon: ArrowPathIcon },
  { kind: "improve", label: "Improve", prompt: "Cải thiện độ rõ ràng, mạch lạc và văn phong học thuật của đoạn này.", Icon: ArrowTrendingUpIcon },
  { kind: "proofread", label: "Proofread", prompt: "Sửa ngữ pháp, chính tả, dấu câu và cách dùng từ chưa tự nhiên.", Icon: CheckCircleIcon },
  { kind: "humanize", label: "Humanize", prompt: "Viết tự nhiên hơn, giảm cách diễn đạt máy móc và lặp cấu trúc.", Icon: UserIcon },
  { kind: "expand", label: "Expand", prompt: "Mở rộng đoạn này bằng giải thích và liên kết lập luận cần thiết.", Icon: ArrowsPointingOutIcon },
  { kind: "shorten", label: "Shorten", prompt: "Rút gọn đoạn này, loại bỏ phần lặp và giữ nguyên nội dung chính.", Icon: ScissorsIcon },
];


// Pure presentation. The parent (ChapterEditor) mounts this inside TipTap's
// BubbleMenu, which handles visibility based on selection state.
//
// Notion-style: a light bar with an "Ask AI ▾" dropdown holding the rewrite
// actions (one vertical list, Heroicon + label), rather than a wide row of
// emoji buttons that wrapped onto two lines. Translate and Cite stay direct on
// the bar because each opens its own picker (TranslateMenu / CitePopover).
export function SelectionToolbar({
  onRewrite, onTranslate, onCite,
}: Props) {
  const [aiOpen, setAiOpen] = useState(false);
  const [rewriteKind, setRewriteKind] = useState<RewriteKind>("improve");
  const [prompt, setPrompt] = useState("");
  const [menuAnchor, setMenuAnchor] = useState<{ left: number; top: number; placement: "top" | "bottom" } | null>(null);
  const askButtonRef = useRef<HTMLButtonElement>(null);

  const toggleAiMenu = () => {
    if (aiOpen) { setAiOpen(false); return; }
    const rect = askButtonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const menuWidth = 360;
    const menuHeight = 430;
    const gap = 8;
    const opensBelow = rect.bottom + gap + menuHeight <= window.innerHeight - 12;
    setMenuAnchor({
      left: Math.max(12, Math.min(window.innerWidth - menuWidth - 12, rect.left)),
      top: opensBelow ? rect.bottom + gap : Math.max(12, rect.top - menuHeight - gap),
      placement: opensBelow ? "bottom" : "top",
    });
    setAiOpen(true);
  };

  const submitRewrite = () => {
    const instruction = prompt.trim();
    if (!instruction) return;
    onRewrite(rewriteKind, instruction);
    setAiOpen(false);
  };

  const barBtn = "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 hover:bg-ink-100 active:scale-[0.98] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200";

  return (
    <div
      className="relative inline-flex items-center gap-0.5 rounded-xl border border-ink-200 bg-white/95 p-1.5 text-[13px] font-medium text-ink-800 shadow-[0_12px_35px_rgba(24,31,50,0.16)] backdrop-blur"
      // TipTap listens above this portal and otherwise tears the BubbleMenu
      // down before a button receives its click. Treat interaction inside the
      // toolbar as editor interaction and keep the saved selection intact.
      onPointerDownCapture={event => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <button
        ref={askButtonRef}
        type="button"
        onPointerDownCapture={event => event.preventDefault()}
        onClick={toggleAiMenu}
        aria-haspopup="menu"
        aria-expanded={aiOpen}
        className={`${barBtn} ${aiOpen ? "bg-ink-100" : ""}`}
      >
        <SparklesIcon className="w-4 h-4 text-primary-600" />
        Ask AI
        <ChevronDownIcon className="w-3 h-3 opacity-60" />
      </button>

      <span className="w-px h-4 bg-ink-200 mx-0.5" aria-hidden />

      <button
        type="button"
        onClick={onTranslate}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") onTranslate(); }}
        className={barBtn}
      >
        <LanguageIcon className="w-4 h-4 text-ink-500" />
        Translate
      </button>
      <button
        type="button"
        onClick={onCite}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") onCite(); }}
        className={barBtn}
      >
        <PaperClipIcon className="w-4 h-4 text-ink-500" />
        Cite
      </button>

      {aiOpen && menuAnchor && typeof document !== "undefined" && createPortal(
        <>
          {/* click-away */}
          <div className="fixed inset-0 z-[90]" onClick={() => setAiOpen(false)} aria-hidden />
          <div
            role="menu"
            data-placement={menuAnchor.placement}
            style={{ left: menuAnchor.left, top: menuAnchor.top }}
            className="fixed z-[100] w-[min(360px,calc(100vw-24px))] rounded-2xl border border-ink-100 bg-white p-3 shadow-[0_18px_45px_rgba(24,31,50,0.18)]"
            onPointerDownCapture={event => {
              event.stopPropagation();
            }}
          >
            <label className="block text-xs font-semibold text-ink-600" htmlFor="selection-ai-prompt">Bạn muốn AI chỉnh đoạn này như thế nào?</label>
            <textarea
              id="selection-ai-prompt"
              autoFocus
              value={prompt}
              maxLength={2000}
              rows={4}
              onChange={event => setPrompt(event.target.value)}
              onKeyDown={event => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submitRewrite();
              }}
              placeholder="Ví dụ: Viết rõ hơn mối quan hệ giữa hai khái niệm, giữ nguyên citation…"
              className="mt-2 w-full resize-none rounded-xl border border-ink-200 px-3 py-2.5 text-sm leading-5 text-ink-900 outline-none placeholder:text-ink-400 focus:border-primary-400 focus:ring-2 focus:ring-primary-100"
            />
            <p className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Prompt mẫu</p>
            <div className="grid grid-cols-2 gap-1">
            {PRESETS.map(({ kind, label, Icon, prompt: presetPrompt }) => (
              <button
                key={label}
                type="button"
                role="menuitem"
                onClick={() => { setRewriteKind(kind); setPrompt(presetPrompt); }}
                className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${rewriteKind === kind && prompt === presetPrompt ? "bg-primary-50 text-primary-700" : "text-ink-700 hover:bg-ink-50"}`}
              >
                <Icon className="w-4 h-4 text-ink-500 shrink-0" />
                {label}
              </button>
            ))}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-ink-100 pt-3">
              <span className="text-[11px] text-ink-400">⌘ Enter để gửi</span>
              <button type="button" disabled={!prompt.trim()} onClick={submitRewrite} className="rounded-lg bg-primary-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-40">Tạo đề xuất</button>
            </div>
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
