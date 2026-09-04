"use client";

import { useState } from "react";
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

  const aiActions: { label: string; Icon: typeof SparklesIcon; on: () => void }[] = [
    { label: "Paraphrase", Icon: ArrowPathIcon, on: onParaphrase },
    { label: "Improve", Icon: ArrowTrendingUpIcon, on: onImprove },
    { label: "Proofread", Icon: CheckCircleIcon, on: onProofread },
    { label: "Humanize", Icon: UserIcon, on: onHumanize },
    { label: "Expand", Icon: ArrowsPointingOutIcon, on: onExpand },
    { label: "Shorten", Icon: ScissorsIcon, on: onShorten },
  ];

  const barBtn = "inline-flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-ink-100 transition-colors";

  return (
    <div className="relative inline-flex items-center gap-0.5 bg-white border border-ink-200 rounded-lg shadow-lg p-1 text-[13px] font-medium text-ink-800">
      <button
        type="button"
        onClick={() => setAiOpen(o => !o)}
        aria-haspopup="menu"
        aria-expanded={aiOpen}
        className={`${barBtn} ${aiOpen ? "bg-ink-100" : ""}`}
      >
        <SparklesIcon className="w-4 h-4 text-primary-600" />
        Ask AI
        <ChevronDownIcon className="w-3 h-3 opacity-60" />
      </button>

      <span className="w-px h-4 bg-ink-200 mx-0.5" aria-hidden />

      <button type="button" onClick={onTranslate} className={barBtn}>
        <LanguageIcon className="w-4 h-4 text-ink-500" />
        Translate
      </button>
      <button type="button" onClick={onCite} className={barBtn}>
        <PaperClipIcon className="w-4 h-4 text-ink-500" />
        Cite
      </button>

      {aiOpen && (
        <>
          {/* click-away */}
          <div className="fixed inset-0 z-40" onClick={() => setAiOpen(false)} aria-hidden />
          <div
            role="menu"
            className="absolute left-0 top-full mt-1 z-50 w-52 bg-white border border-ink-200 rounded-xl shadow-xl p-1"
          >
            {aiActions.map(({ label, Icon, on }) => (
              <button
                key={label}
                type="button"
                role="menuitem"
                onClick={() => { on(); setAiOpen(false); }}
                className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md hover:bg-ink-50 text-left text-ink-800"
              >
                <Icon className="w-4 h-4 text-ink-500 shrink-0" />
                {label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
