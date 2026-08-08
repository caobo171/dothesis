import { Loader2 } from "lucide-react";

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


/**
 * Collapse runs of the same message.
 *
 * The engine narrates per call, not per distinct activity, so a turn that
 * reads two skills and looks two things up printed "Looking something up… /
 * Reading the guide for this step… / Looking something up… / Reading the guide
 * for this step…". Four lines of scroll that say two things — and the repeats
 * crowd out the earlier lines that WERE different, because only the last few
 * are shown. Repeats become a ×N on one line instead.
 */
export function dedupeProgress(items: ProgressItem[]): (ProgressItem & { times: number })[] {
  const out: (ProgressItem & { times: number })[] = [];
  for (const p of items || []) {
    const prev = out[out.length - 1];
    if (prev && prev.message === p.message) prev.times += 1;
    else out.push({ ...p, times: 1 });
  }
  return out;
}


export function ProgressBubble({
  progress,
  moduleTag,
}: {
  progress: ProgressItem[];
  moduleTag?: string | null;
}) {
  // Deduped FIRST, then windowed — windowing first would spend the window on
  // repeats and hide the distinct steps behind them.
  const all = dedupeProgress(progress);
  const visible = all.slice(-4);
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
      {/* Headline + rule, like the reference's thinking block: one line saying
          what is happening now, with the trail hung off a hairline beneath it.
          The trail is there to show motion, not to be read, so it fades out
          upward instead of competing for attention. */}
      <div
        className="flex items-center gap-2 text-[13px] text-ink-500 mb-1.5"
        data-testid="progress-line-current"
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" aria-hidden />
        <span className="truncate">{last ? last.message : "Đang xử lý…"}</span>
      </div>
      {visible.length > 1 && (
        <div
          className="border-l border-ink-200 pl-3.5 flex flex-col gap-1 text-[12.5px] min-w-[260px]"
          // Older lines fade toward the top — motion without a second column of
          // text asking to be read.
          style={{
            maskImage: "linear-gradient(to bottom, transparent, black 55%)",
            WebkitMaskImage: "linear-gradient(to bottom, transparent, black 55%)",
          }}
        >
          {visible.slice(0, -1).map((p, i) => (
            <div key={i} className="text-ink-400 truncate" data-testid="progress-line-prev">
              {p.message}
              {p.times > 1 && <span className="text-ink-300"> ×{p.times}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
