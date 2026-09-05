/** Straight answers. One panel open at a time. */
"use client";

import { useId, useState } from "react";

import { IconPlus, SectionHead } from "./shared";

const ITEMS: Array<[string, string]> = [
  [
    // The old answer was a flat "No", which the rest of the page contradicts:
    // Auto Thesis really does run every module unattended from one prompt. The
    // honest answer is that both modes exist and the student picks.
    "Does DoThesis write my thesis for me?",
    "It can, and that's your choice. Auto Thesis drafts every module from one prompt while you watch, and you can stop it at any point. Or work module by module in chat, approving each direction and writing in your own voice. Either way you are the author, and the work is yours to check.",
  ],
  [
    // Was "Only from the sources you provide and from CrossRef" — not true.
    // M2's default path is a deep search across several academic APIs plus
    // grounded web search; Crossref is one backend, and a result is accepted on
    // a DOI *or* a URL, so "exact and definitive" oversold it.
    "Where do the citations come from?",
    "It searches the academic databases — Crossref, OpenAlex, Semantic Scholar — and the open web, and you can add your own PDFs and DOIs. Sources with a DOI are the strongest; ones found without one are kept but not treated as confirmed. When a chapter is written, any citation that isn't in the project's reference list is stripped out.",
  ],
  [
    "Will it change my numbers or results?",
    "Never silently. Any rewrite that would alter a number, statistic or citation is discarded and your original text is kept unchanged.",
  ],
  [
    "Is this an AI detector? Will it beat Turnitin?",
    "No. The writing-rhythm and similarity tools give you writing feedback and a self-check over your own file. They do not predict Turnitin or any commercial detector, and a low score is not a pass.",
  ],
  [
    "Is DoThesis multilingual?",
    "Yes — the product is fully bilingual in English and Tiếng Việt, and can draft and cite in either.",
  ],
  [
    "How is it priced?",
    "In credits, not a flat subscription. You start with free credits and pay per run, so you see exactly what each piece of work costs. No card required to begin.",
  ],
];

function FaqItem({
  q,
  a,
  open,
  onToggle,
  panelId,
}: {
  q: string;
  a: string;
  open: boolean;
  onToggle: () => void;
  panelId: string;
}) {
  return (
    <div style={{ borderBottom: "1px solid var(--ink-200)" }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          padding: "22px 4px",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span
          style={{ fontSize: 16.5, fontWeight: 700, color: "var(--ink-900)" }}
        >
          {q}
        </span>
        <span
          aria-hidden="true"
          style={{
            flexShrink: 0,
            color: "var(--ink-400)",
            transform: open ? "rotate(45deg)" : "none",
            transition: "transform .2s",
          }}
        >
          <IconPlus size={18} />
        </span>
      </button>
      <div
        id={panelId}
        // max-height animates; the panel stays in the DOM so the collapse has
        // something to transition against.
        style={{
          maxHeight: open ? 260 : 0,
          overflow: "hidden",
          transition: "max-height .3s ease",
        }}
      >
        <p
          style={{
            fontSize: 14.5,
            color: "var(--ink-500)",
            lineHeight: 1.65,
            padding: "0 4px 22px",
            maxWidth: 660,
          }}
        >
          {a}
        </p>
      </div>
    </div>
  );
}

export function Faq() {
  const [open, setOpen] = useState(0);
  const base = useId();

  return (
    <section id="faq" className="lp-sec" style={{ background: "var(--ink-50)" }}>
      <div className="lp-wrap-narrow">
        <SectionHead eyebrow="Questions" title="Straight answers." />
        <div style={{ marginTop: 40 }}>
          {ITEMS.map(([q, a], i) => (
            <FaqItem
              key={q}
              q={q}
              a={a}
              open={open === i}
              onToggle={() => setOpen(open === i ? -1 : i)}
              panelId={`${base}-faq-${i}`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
