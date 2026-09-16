"use client";

import { ListTree } from "lucide-react";
import { CHAPTER_ORDER, type ChapterName } from "./OutlineRail";


type TocItem = { chapter: ChapterName; level: number; text: string; index: number };


/** Editor preview of the same heading-derived TOC the export pipeline builds.
 * It is generated UI rather than stored prose, so renaming a heading cannot
 * leave a stale hand-written contents page behind. */
export function DocumentToc({
  title,
  items,
  onSelect,
  onSelectChapter,
}: {
  title: string;
  items: TocItem[];
  onSelect: (chapter: ChapterName, index: number) => void;
  onSelectChapter: (chapter: ChapterName) => void;
}) {
  return (
    <section className="document-toc" data-testid="document-toc" aria-label="Mục lục tài liệu">
      <div className="document-toc-kicker"><ListTree className="h-3.5 w-3.5" /> Document contents</div>
      <h1>{title || "Luận văn"}</h1>
      <h2>Mục lục</h2>
      <ol>
        {CHAPTER_ORDER.map((chapter, chapterIndex) => {
          const chapterItems = items.filter(item => item.chapter === chapter.name);
          if (chapterItems.length === 0) return null;
          const baseLevel = Math.min(...chapterItems.map(item => item.level));
          const shortLabel = chapter.label.replace(/^Ch \d+ - /, "");
          return (
            <li key={chapter.name} className="document-toc-chapter">
              <button type="button" onClick={() => onSelectChapter(chapter.name)} title={shortLabel}>
                <span>Chương {chapterIndex + 1} · {shortLabel}</span>
                <span className="document-toc-leader" aria-hidden />
              </button>
              <ol>
                {chapterItems.map(item => (
                  <li key={`${item.chapter}-${item.index}-${item.text}`} style={{ paddingLeft: `${24 + (item.level - baseLevel) * 24}px` }}>
                    <button type="button" onClick={() => onSelect(item.chapter, item.index)} title={item.text}>
                      <span>{item.text}</span>
                      <span className="document-toc-leader" aria-hidden />
                    </button>
                  </li>
                ))}
              </ol>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
