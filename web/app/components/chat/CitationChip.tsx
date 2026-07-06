"use client";

import { FileText, Globe } from "lucide-react";

/**
 * Inline grounding pill — Google AI-Overview style. The agent emits
 * `{{cite: label | title | url}}` markers next to grounded claims (see
 * agent/runtime.py "Grounding"); MessageBubble splits them out of the prose and
 * renders this pill. Whole pill is a link to the source; hovering shows a card
 * with the full title + source kind.
 *
 * Kind detection: a DOI link (or `doi:` ref) → an academic paper (M2+ grounding);
 * anything else → a web source (allowed for M1 / early research). Drives the icon
 * + label so the user can tell verified papers from web at a glance.
 */
export function CitationChip({ label, title, url }: { label: string; title: string; url: string }) {
  const isPaper = /doi\.org|(^|\s)doi:/i.test(url) || /doi:/i.test(label);
  const href = url.replace(/^doi:\s*/i, "https://doi.org/");
  const Icon = isPaper ? FileText : Globe;
  return (
    <span className="group relative inline-flex align-baseline">
      <a
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-1 mx-0.5 px-1.5 py-[1px] rounded-full bg-ink-100 hover:bg-primary-50 text-ink-500 hover:text-primary-700 text-[11px] font-medium no-underline align-middle transition-colors"
      >
        <Icon className="w-3 h-3 shrink-0" />
        {label}
      </a>
      {/* Hover card (preview only — the pill itself is the link). */}
      <span className="pointer-events-none absolute bottom-full left-0 mb-1.5 z-50 hidden group-hover:block w-64 rounded-xl border border-ink-200 bg-white shadow-xl p-3 text-left normal-case">
        <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.06em] font-bold text-ink-400">
          <Icon className="w-3 h-3" /> {isPaper ? "Paper" : "Web source"}
        </span>
        <span className="block text-[12.5px] font-semibold text-ink-900 leading-snug mt-1">{title}</span>
        <span className="block text-[11px] text-primary-600 mt-1.5 truncate">{label} · open ↗</span>
      </span>
    </span>
  );
}
