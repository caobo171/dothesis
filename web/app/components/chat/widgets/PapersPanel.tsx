"use client";

import { useState } from "react";
import { ArrowUpRight, Flag, Quote } from "lucide-react";

import type { PapersPanelHint } from "./types";


/**
 * Foundational citations panel — matches DoThesis-standalone:
 *   - White card with ink-200 border + rounded-2xl
 *   - Header strip (ink-50 bg) with title, paper count chip, APA style label
 *   - Per-camp sections: small color dot + ALL-CAPS label + paper count
 *   - Per-paper row: PDF thumbnail (gradient bg, optional seminal ⭐),
 *     author (year), cites pill, title, venue/DOI, page-cited quote in
 *     violet-rail blockquote, ⤴ / " " / ✕ action column
 *   - Footer strip with "Add from Semantic Scholar" / "Open full library"
 *
 * Click behavior:
 *   - Paper title → open DOI URL in new tab (when `doi` is set)
 *   - ⤴ action → open PDF at the cited page (`pdf_url + #page=p`) when set
 *   - " " action → fires onCite(paperId, quote) for citation manager
 *   - ✕ action → fires onFlag(paperId) so the user can remove a bad row
 *
 * The agent emits this via the `[PAPERS] {json} [/PAPERS]` marker (see
 * agent/runtime.py); chat_v3 persists it as the assistant message's
 * tool_calls_json so it survives reload.
 */
export function PapersPanel({
  hint,
  onCite,
  onFlag,
}: {
  hint: PapersPanelHint;
  onCite?: (paperId: string, quote: string) => void;
  onFlag?: (paperId: string) => void;
}) {
  // Tracks which camps are collapsed — defaults to all expanded. Click on
  // a camp header collapses/expands it. Useful when the agent surfaces a
  // panel with 5+ camps and the user wants to scan headlines first.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const total = hint.camps.reduce((s, c) => s + c.papers.length, 0);
  const indexed = hint.indexed_count ?? total;

  return (
    <div
      className="mt-2.5 rounded-2xl border border-ink-200 bg-white overflow-hidden"
      data-testid="papers-panel"
    >
      {/* Header */}
      <div className="px-3.5 py-2.5 bg-ink-50 border-b border-ink-200 flex items-center gap-2">
        <span className="text-[13px] font-bold">📚 {hint.title ?? "Foundational citations"}</span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 text-[11px] font-semibold">
          {total} seminal · {indexed} indexed
        </span>
        <span className="flex-1" />
        <span className="text-[11px] text-ink-500">{hint.style ?? "APA 7"}</span>
      </div>

      {/* Camps */}
      <div className="py-1">
        {hint.camps.map((camp, idx) => {
          const isCollapsed = !!collapsed[camp.id];
          return (
            <div key={camp.id}>
              {/* Camp header (clickable to toggle) */}
              <button
                type="button"
                onClick={() => setCollapsed(prev => ({ ...prev, [camp.id]: !prev[camp.id] }))}
                className="w-full px-4 pt-3 pb-1.5 flex items-center gap-2 text-left hover:bg-ink-50/60 transition-colors"
              >
                <span
                  className="w-2 h-2 rounded-sm shrink-0"
                  style={{ background: CAMP_COLORS[idx % CAMP_COLORS.length] }}
                />
                <span className="text-[11px] uppercase tracking-[0.06em] font-bold text-ink-500">
                  {camp.label}
                </span>
                <span className="flex-1" />
                <span className="text-[11px] text-ink-400 font-medium">
                  {camp.papers.length} papers
                </span>
                <span className="text-ink-400 text-[10px]">{isCollapsed ? "▸" : "▾"}</span>
              </button>

              {!isCollapsed && camp.papers.map(p => (
                <PaperRow
                  key={p.id}
                  paper={p}
                  onCite={onCite}
                  onFlag={onFlag}
                />
              ))}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-3.5 py-2.5 bg-ink-50 border-t border-ink-200 flex items-center gap-2 text-[12px] text-ink-600">
        <span>{hint.footer_note ?? "✓ Click any title to open the source"}</span>
        <span className="flex-1" />
      </div>
    </div>
  );
}


// --- single paper row ---

function PaperRow({
  paper, onCite, onFlag,
}: {
  paper: PapersPanelHint["camps"][number]["papers"][number];
  onCite?: (paperId: string, quote: string) => void;
  onFlag?: (paperId: string) => void;
}) {
  const cited_url = paper.pdf_url
    ? (paper.page != null ? `${paper.pdf_url}#page=${paper.page}` : paper.pdf_url)
    : null;
  const doi_url = paper.doi ? `https://doi.org/${paper.doi}` : null;
  const title_link = doi_url ?? cited_url;

  return (
    <div className="px-4 pt-3 pb-3.5 border-t border-ink-100 flex gap-3.5 items-start">
      {/* PDF thumbnail */}
      <div
        className="relative w-[38px] min-w-[38px] h-[48px] rounded-md border border-ink-200 flex items-end justify-center"
        style={{
          background: "linear-gradient(135deg, #F1F3FF 0%, #F4F0FF 100%)",
          boxShadow: "1px 1px 0 var(--ink-200, #E4E7F1)",
        }}
        aria-hidden="true"
      >
        {paper.seminal && (
          <span
            className="absolute -top-1.5 -right-1.5 w-[18px] h-[18px] rounded-full bg-amber-500 text-white inline-flex items-center justify-center text-[10px] font-extrabold"
            title="Seminal"
          >
            ★
          </span>
        )}
        <span className="text-[9px] font-extrabold text-primary-600 pb-0.5">PDF</span>
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-[13.5px] font-bold text-ink-900">{paper.author}</span>
          <span className="text-[12.5px] text-ink-500">({paper.year})</span>
          {paper.cites != null && (
            <span className="text-[11px] text-primary-700 bg-primary-50 px-1.5 py-0.5 rounded-full font-semibold">
              {paper.cites.toLocaleString()} cites
            </span>
          )}
        </div>
        {title_link ? (
          <a
            href={title_link}
            target="_blank"
            rel="noreferrer noopener"
            className="block text-[13.2px] text-ink-800 hover:text-primary-700 hover:underline leading-snug mt-1 font-medium"
          >
            {paper.title}
          </a>
        ) : (
          <div className="text-[13.2px] text-ink-800 leading-snug mt-1 font-medium">
            {paper.title}
          </div>
        )}
        <div className="text-[11.5px] text-ink-500 mt-1 italic">
          {paper.venue}
          {paper.vol ? `, ${paper.vol}` : null}
          {paper.doi && (
            <> · <span className="font-mono not-italic">doi:{paper.doi}</span></>
          )}
        </div>
        {paper.quote && (
          <blockquote
            className="mt-2 py-2 pl-3 pr-2.5 rounded-r-lg text-[13px] text-ink-800 leading-relaxed font-serif"
            style={{
              borderLeft: "3px solid #6A4DE0",
              background: "#F4F0FF",
            }}
          >
            {paper.quote}
            {paper.page != null && (
              <span className="not-italic text-ink-500 text-[11.5px] ml-1">(p. {paper.page})</span>
            )}
          </blockquote>
        )}
      </div>

      {/* Per-paper actions */}
      <div className="flex flex-col gap-1 ml-1">
        {cited_url && (
          <a
            href={cited_url}
            target="_blank"
            rel="noreferrer noopener"
            title={paper.page != null ? `Open PDF at p.${paper.page}` : "Open PDF"}
            className="w-[26px] h-[26px] rounded-md inline-flex items-center justify-center bg-white border border-ink-200 text-ink-600 hover:bg-primary-50 hover:text-primary-700 hover:border-primary-200 transition-colors"
          >
            <ArrowUpRight className="w-3.5 h-3.5" />
          </a>
        )}
        {paper.quote && onCite && (
          <button
            type="button"
            onClick={() => onCite(paper.id, paper.quote!)}
            title="Insert citation"
            className="w-[26px] h-[26px] rounded-md inline-flex items-center justify-center bg-white border border-ink-200 text-ink-600 hover:bg-primary-50 hover:text-primary-700 hover:border-primary-200 transition-colors"
          >
            <Quote className="w-3.5 h-3.5" />
          </button>
        )}
        {onFlag && (
          <button
            type="button"
            onClick={() => onFlag(paper.id)}
            title="Flag / remove"
            className="w-[26px] h-[26px] rounded-md inline-flex items-center justify-center bg-white border border-ink-200 text-ink-500 hover:bg-amber-50 hover:text-amber-700 hover:border-amber-200 transition-colors"
          >
            <Flag className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}


// Camp swatch colors — match the design's 4-color palette (primary,
// accent-violet, review-600, ok-600). When there are more than 4 camps the
// palette wraps; that's the design's intentional behavior too.
const CAMP_COLORS = [
  "#2540FF",  // primary
  "#6A4DE0",  // accent-violet
  "#E08800",  // review-600 (amber)
  "#1F9D62",  // ok-600 (emerald)
];
