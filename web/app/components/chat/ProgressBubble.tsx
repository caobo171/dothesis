/**
 * Live engine-progress indicator.
 *
 * Shown in the same slot as ThinkingBubble (between the user's message and
 * the first agent SSE token) when the backend streams `type: progress`
 * events — currently M2 phase2 during the 30-60s citation scout. The
 * latest message is the headline; the previous 2-3 stay visible in muted
 * grey so the user gets a sense of motion.
 *
 * Why this exists: a bare typing dot during a 60-second wait reads as
 * "stalled". The engine already knows what stage it's in (Researching:
 * <topic>, API chain: gemini_grounded → crossref, Trying Gemini Grounded,
 * ...) — surfacing that turns dead air into clear progress.
 */
export type ProgressItem = { stage: string; message: string };


export function ProgressBubble({
  progress,
  moduleTag,
}: {
  progress: ProgressItem[];
  moduleTag?: string | null;
}) {
  // Show the latest 4 entries; latest at the bottom mirrors how the
  // engine itself prints to stdout, so the user can follow line-by-line.
  const visible = progress.slice(-4);
  const last = visible[visible.length - 1];

  return (
    // Work-in-progress is CHROME, not prose: sans-serif, small, hung off a
    // hairline rule like the reference's thinking block, so it reads as the
    // machine narrating itself rather than as part of the answer. The old
    // version put it in the same white card the reply used, which gave a
    // transient "Trying Crossref…" the same visual weight as the thesis text.
    <div data-role="assistant" data-testid="progress-bubble" className="flex flex-col">
      {moduleTag && (
        <div className="flex items-center gap-2 mb-2">
          <span className="px-[7px] py-[2px] rounded-md bg-ink-100 text-ink-600 font-serif font-extrabold text-[11px] tracking-[0.03em]">
            {moduleTag}
          </span>
        </div>
      )}
      <div className="border-l border-ink-200 pl-3.5 flex flex-col gap-1 text-[13px] min-w-[260px]">
        {/* Earlier entries — muted so the eye lands on the latest line.
            Capped at last 4 so the block doesn't grow unbounded; the
            raw stream stays in useChat.streamingProgress in case a
            future debug view wants to show them all. */}
        {visible.slice(0, -1).map((p, i) => (
          <div
            key={i}
            className="text-[12.5px] text-ink-400 truncate"
            data-testid="progress-line-prev"
          >
            {p.message}
          </div>
        ))}

        {last && (
          <div
            className="flex items-center gap-2 text-ink-600"
            data-testid="progress-line-current"
          >
            <span
              className="h-1.5 w-1.5 rounded-full bg-ink-400 animate-pulse shrink-0"
              aria-hidden="true"
            />
            <span className="truncate">{last.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}
