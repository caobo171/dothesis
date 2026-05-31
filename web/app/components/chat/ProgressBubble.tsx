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
    <div
      className="flex justify-start mb-3"
      data-role="assistant"
      data-testid="progress-bubble"
    >
      <div className="max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-3 border border-gray-200 min-w-[280px]">
        {moduleTag && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-2">
            {moduleTag}
          </div>
        )}

        <div className="flex flex-col gap-1 text-sm">
          {/* Earlier entries — muted so the eye lands on the latest line.
              Capped at last 4 so the bubble doesn't grow unbounded; the
              raw stream stays in useChat.streamingProgress in case a
              future debug view wants to show them all. */}
          {visible.slice(0, -1).map((p, i) => (
            <div
              key={i}
              className="text-xs text-gray-400 truncate"
              data-testid="progress-line-prev"
            >
              {p.message}
            </div>
          ))}

          {/* Latest line — bold, with a small animated indicator. */}
          {last && (
            <div
              className="flex items-center gap-2 text-gray-900"
              data-testid="progress-line-current"
            >
              <span
                className="h-2 w-2 rounded-full bg-purple-500 animate-pulse"
                aria-hidden="true"
              />
              <span className="truncate">{last.message}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
