/**
 * The right-hand column of AuthShell: what DoThesis does, shown rather than
 * claimed.
 *
 * It renders the landing hero's own demo — the same component, not a copy —
 * so the door and the shop window can never disagree about what the product
 * produces.
 *
 * Two things this file is responsible for on behalf of that component:
 *
 *   1. Importing landing.css. It is otherwise imported only by the landing
 *      page, so on /login and /signup nothing would define --primary-*,
 *      --moss-* or the .lp-* classes and the mock would render unstyled.
 *   2. The `.lp-root` wrapper. landing.css scopes its token block to that
 *      class specifically so importing it cannot re-tune the rest of the app;
 *      without the wrapper the tokens exist in the stylesheet and apply to
 *      nothing.
 *
 * The ~50 `.lp-*` / `.ds-*` rules the import also brings along are inert here:
 * neither namespace appears anywhere in the app shell.
 */
"use client";

import "@/app/landing/landing.css";

import { ProductMock } from "@/app/landing/_components/ProductMock";

export function AuthExplainer() {
  return (
    // 560 rather than the hero's 980: at the "done" step the page is zoomed to
    // fit the frame's HEIGHT, so a wide frame just adds white to either side of
    // a small document. A narrower column puts the finished thesis nearer the
    // middle of its own card. Still clears 1280 — the xl breakpoint leaves this
    // column 624px inside its padding.
    //
    // background:transparent because .lp-root carries `background: #fff` — on
    // the landing page it IS the page shell, so that is correct there. Here it
    // is a content-sized box sitting on the shell's gradient, and the white
    // paints a hard-edged slab behind the heading with no padding of its own,
    // clipping the card's shadow at its corners. Inline so it beats the class
    // regardless of how the utility and stylesheet layers end up ordered.
    <div className="lp-root w-full max-w-[560px]" style={{ background: "transparent" }}>
      <div className="lp-eyebrow" style={{ color: "var(--primary-600)" }}>
        Idea → thesis
      </div>
      <h2
        className="lp-display"
        style={{
          marginTop: 10,
          fontSize: 26,
          letterSpacing: "-0.028em",
          lineHeight: 1.2,
        }}
      >
        One thread, from a topic idea to a submitted draft.
      </h2>

      {/* Shorter than the hero's 600/420: this column is a viewport tall with
          a heading above it, not a hero with the whole page below to spill
          into. ProductMock measures its zoom against these, so the finished
          thesis still fits the frame exactly. */}
      <div style={{ marginTop: 22 }}>
        <ProductMock doneHeight={480} writingHeight={340} />
      </div>
    </div>
  );
}
