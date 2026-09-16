"use client";

import { useState } from "react";
import { BookOpen, ListTree } from "lucide-react";


export type ChapterName = "intro" | "lit_review" | "methodology" | "results" | "conclusion";


// FIVE chapters, not six: the discussion of findings lives INSIDE Chapter 5
// rather than as a chapter of its own, matching the backend's collapsed
// M5_CHAPTER_ORDER / M5_CHAPTER_TITLES (orchestrator/tools/m5_writing.py).
//
// Exported so any other web surface that needs "how many chapters does a
// finished thesis have" (e.g. ModuleSlices' M5Body progress line) derives it
// from here instead of hardcoding a number that can drift out of sync — a
// hardcoded `6` is exactly how the retired sixth chapter kept showing up
// after the backend collapsed to five.
export const CHAPTER_ORDER: { name: ChapterName; label: string }[] = [
  { name: "intro",        label: "Ch 1 - Introduction" },
  { name: "lit_review",   label: "Ch 2 - Literature Review" },
  { name: "methodology",  label: "Ch 3 - Methodology" },
  { name: "results",      label: "Ch 4 - Results" },
  { name: "conclusion",   label: "Ch 5 - Conclusions and Recommendations" },
];


type Props = {
  present: ChapterName[];
  active: ChapterName;
  onSelect: (name: ChapterName) => void;
  contents?: Array<{ chapter: ChapterName; level: number; text: string; index: number }>;
  onSelectHeading?: (chapter: ChapterName, index: number) => void;
};


// Left rail. Pure presentation — save-before-switch logic lives in
// the parent so the rail stays unit-testable without server coupling.
export function OutlineRail({ present, active, onSelect, contents = [], onSelectHeading }: Props) {
  const [tab, setTab] = useState<"chapters" | "contents">("chapters");
  return (
    <nav aria-label="Chapters" className="editor-outline-rail w-[236px] shrink-0 overflow-y-auto border-r border-ink-100 bg-[#fbfbfa] px-3 py-5">
      <div className="mb-4 flex items-center justify-between px-2">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.08em] text-ink-400">DOCUMENT</div>
          <div className="mt-0.5 text-sm font-semibold text-ink-900">Outline</div>
        </div>
        <span className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-ink-500">
          {present.length}/5
        </span>
      </div>
      <div className="mb-3 grid grid-cols-2 rounded-lg bg-ink-100 p-1" role="tablist" aria-label="Document navigation">
        <RailTab active={tab === "chapters"} onClick={() => setTab("chapters")} icon={<BookOpen className="h-3.5 w-3.5" />}>
          Chương
        </RailTab>
        <RailTab active={tab === "contents"} onClick={() => setTab("contents")} icon={<ListTree className="h-3.5 w-3.5" />}>
          Mục lục
        </RailTab>
      </div>
      {tab === "chapters" ? <div className="space-y-1">
      {CHAPTER_ORDER.map(({ name, label }) => {
        const isPresent = present.includes(name);
        const isActive = name === active;
        const chapterNo = CHAPTER_ORDER.findIndex(chapter => chapter.name === name) + 1;
        const shortLabel = label.replace(/^Ch \d+ - /, "");
        return (
          <button
            key={name}
            disabled={!isPresent}
            aria-current={isActive ? "true" : undefined}
            onClick={() => onSelect(name)}
            className={
              "group relative flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 " +
              (isActive
                ? "bg-white text-primary-700 shadow-[0_1px_5px_rgba(24,31,50,0.08)] ring-1 ring-ink-100"
                : isPresent
                ? "text-ink-600 hover:bg-white hover:text-ink-900"
                : "text-gray-400 cursor-not-allowed")
            }
          >
            <span className={"mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[10px] font-bold tabular-nums " + (isActive ? "bg-primary-600 text-white" : "bg-ink-100 text-ink-500")}>
              {chapterNo}
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-medium leading-5">{shortLabel}</span>
              <span className="block text-[10px] leading-4 text-ink-400">Chapter {chapterNo}</span>
            </span>
          </button>
        );
      })}
      </div> : (
        <div className="space-y-0.5" role="tabpanel" aria-label="Mục lục">
          {contents.length === 0 ? (
            <div className="px-2 py-6 text-center text-xs leading-5 text-ink-400">Chưa có tiêu đề trong tài liệu.</div>
          ) : CHAPTER_ORDER.filter(chapter => present.includes(chapter.name)).map((chapter, chapterIndex) => {
            const chapterItems = contents.filter(item => item.chapter === chapter.name);
            if (chapterItems.length === 0) return null;
            // Decision: normalize indentation inside each chapter. Imported
            // Markdown may begin at H1 or H2, but those differences must not
            // make one chapter look nested under the previous chapter.
            const baseLevel = Math.min(...chapterItems.map(item => item.level));
            const chapterNo = CHAPTER_ORDER.findIndex(item => item.name === chapter.name) + 1;
            const shortLabel = chapter.label.replace(/^Ch \d+ - /, "");
            const isActive = chapter.name === active;
            return (
              <section key={chapter.name} className={chapterIndex > 0 ? "mt-2 border-t border-ink-100 pt-2" : undefined}>
                <button
                  type="button"
                  onClick={() => onSelect(chapter.name)}
                  className={"group flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 " +
                    (isActive ? "text-primary-700" : "text-ink-700")}
                >
                  <span className={"mt-[6px] h-2 w-2 shrink-0 rounded-[3px] " + (isActive ? "bg-primary-600" : "bg-ink-400 group-hover:bg-primary-400")} />
                  <span className="min-w-0">
                    <span className="block text-[10px] font-bold uppercase tracking-[0.08em]">Chương {chapterNo}</span>
                    <span className="mt-0.5 block line-clamp-2 text-[11px] leading-4 text-ink-500">{shortLabel}</span>
                  </span>
                </button>
                <div className="mt-0.5">
                  {chapterItems.map(item => (
                    <button
                      key={`${item.chapter}-${item.index}-${item.text}`}
                      type="button"
                      title={item.text}
                      onClick={() => onSelectHeading?.(item.chapter, item.index)}
                      className={"group flex w-full items-start gap-2 rounded-lg py-1.5 pr-2 text-left text-[12px] leading-4 transition hover:bg-white hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 " +
                        (isActive ? "text-ink-800" : "text-ink-500")}
                      style={{ paddingLeft: `${20 + (item.level - baseLevel) * 14}px` }}
                    >
                      <span className={"mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full " + (isActive ? "bg-primary-500" : "bg-ink-300 group-hover:bg-primary-400")} />
                      <span className="line-clamp-2 min-w-0">{item.text}</span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </nav>
  );
}


function RailTab({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button type="button" role="tab" aria-selected={active} onClick={onClick}
      className={"inline-flex h-7 items-center justify-center gap-1.5 rounded-md text-[11px] font-semibold transition " +
        (active ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800")}>
      {icon}{children}
    </button>
  );
}
