/**
 * The placeholder a conversation loads behind.
 *
 * Shared by the two routes that can show it, because the student passes
 * through both in one navigation: /chat/projects/[pid] resolves the thread and
 * redirects, then the thread route mounts and fetches. Rendering a line of
 * grey text on the first and bubbles on the second made one navigation look
 * like two different screens, the first of which looked broken.
 *
 * Bubble-shaped and alternating sides so it reads as a conversation arriving
 * rather than as loose bars.
 */
const ROWS: { mine: boolean; lines: string[] }[] = [
  { mine: false, lines: ["w-11/12", "w-4/5"] },
  { mine: true, lines: ["w-3/4"] },
  { mine: false, lines: ["w-full", "w-10/12", "w-7/12"] },
];

export function ThreadSkeleton({ label }: { label?: string }) {
  return (
    <div
      className="flex-1 px-6 py-7 flex flex-col gap-6 max-w-3xl w-full mx-auto"
      aria-busy="true"
      aria-label={label || "Loading conversation"}
    >
      {ROWS.map((row, i) => (
        // `w-`, not `max-w-`. A max-width-only row shrinks to fit its content,
        // and its content is lines sized in PERCENTAGES — which then resolve
        // against a width that does not exist yet. The bubbles collapsed to
        // padding-width pills. A definite width gives the percentages
        // something real to measure.
        <div key={i} className={row.mine ? "self-end w-[62%]" : "self-start w-[82%]"}>
          <div
            className={`rounded-2xl px-4 py-3.5 flex flex-col gap-2.5 ${
              row.mine ? "bg-ink-100/70" : "bg-ink-50 border border-ink-200/70"
            }`}
          >
            {row.lines.map((w, j) => (
              <span key={j} className={`block h-2.5 rounded-full bg-ink-200/80 animate-pulse ${w}`} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
