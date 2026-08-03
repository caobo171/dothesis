import * as React from "react";

import { cn } from "@/app/lib/utils";

// Shared loading placeholder. Data-dependent text used to render as "—", "0"
// or "Loading…" before the first fetch resolved, which reads as a real value
// (zero theses, no credit) until it flips — a skeleton reads as "not yet known".
//
// `tone="dark"` is for skeletons sitting on the ink-900 hero: a light bar on a
// dark surface instead of the default ink-100 bar on white.
// Renders a <span> (display:block by default) rather than a <div> so it can
// also stand in for a word inside a heading without invalid nesting.
export function Skeleton({
  className,
  tone = "light",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "light" | "dark" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "block animate-pulse rounded-md",
        tone === "dark" ? "bg-white/[0.18]" : "bg-ink-100",
        className,
      )}
      {...props}
    />
  );
}
