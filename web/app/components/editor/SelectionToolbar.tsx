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
  onParaphrase: () => void;
  onTranslate: () => void;
  onCite: () => void;
  onProofread: () => void;
  onImprove: () => void;
  onHumanize: () => void;
  onExpand: () => void;
  onShorten: () => void;
};


// Pure presentation. The parent (ChapterEditor) mounts this inside TipTap's
// BubbleMenu, which handles visibility based on selection state.
//
// Notion-style: a light bar with an "Ask AI ▾" dropdown holding the rewrite
// actions (one vertical list, Heroicon + label), rather than a wide row of
// emoji buttons that wrapped onto two lines. Translate and Cite stay direct on
// the bar because each opens its own picker (TranslateMenu / CitePopover).
export function SelectionToolbar({
  onParaphrase, onTranslate, onCite,
  onProofread, onImprove, onHumanize, onExpand, onShorten,
}: Props) {
  const [aiOpen, setAiOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<{ left: number; top: number; placement: "top" | "bottom" } | null>(null);
  const askButtonRef = useRef<HTMLButtonElement>(null);

  const toggleAiMenu = () => {
    if (aiOpen) { setAiOpen(false); return; }
    const rect = askButtonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const menuWidth = 224;
    const menuHeight = 304;
    const gap = 8;
    const opensBelow = rect.bottom + gap + menuHeight <= window.innerHeight - 12;
    setMenuAnchor({
      left: Math.max(12, Math.min(window.innerWidth - menuWidth - 12, rect.left)),
      top: opensBelow ? rect.bottom + gap : Math.max(12, rect.top - menuHeight - gap),
      placement: opensBelow ? "bottom" : "top",
    });
    setAiOpen(true);
  };

  const aiActions: { label: string; Icon: typeof SparklesIcon; on: () => void }[] = [
    { label: "Paraphrase", Icon: ArrowPathIcon, on: onParaphrase },
    { label: "Improve", Icon: ArrowTrendingUpIcon, on: onImprove },
    { label: "Proofread", Icon: CheckCircleIcon, on: onProofread },
    { label: "Humanize", Icon: UserIcon, on: onHumanize },
    { label: "Expand", Icon: ArrowsPointingOutIcon, on: onExpand },
    { label: "Shorten", Icon: ScissorsIcon, on: onShorten },
  ];

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
            className="fixed z-[100] w-56 rounded-xl border border-ink-100 bg-white p-1.5 shadow-[0_18px_45px_rgba(24,31,50,0.18)]"
            onPointerDownCapture={event => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            {aiActions.map(({ label, Icon, on }) => (
              <button
                key={label}
                type="button"
                role="menuitem"
                onPointerDownCapture={event => event.preventDefault()}
                onClick={() => { on(); setAiOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-ink-50 text-left text-ink-800 transition-colors"
              >
                <Icon className="w-4 h-4 text-ink-500 shrink-0" />
                {label}
              </button>
            ))}
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
