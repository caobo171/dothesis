"use client";

import { useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Loader2, Pause, Play, RotateCcw, XCircle } from "lucide-react";

import { ModuleProgressDot, type ModuleStatus } from "./ModuleProgressDot";
import { useAutoThesisRun } from "./hooks/useAutoThesisRun";
import { useArtifactDownload } from "./hooks/useArtifactDownload";
import { apiFetch, swrFetcher as fetcher, triggerExportDownload } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";

/**
 * The workspace WHILE Auto Thesis is running — the main pane, not a panel.
 *
 * It replaced a 480px drawer that floated over the chat thread. That layout
 * made two wrong claims at once: the thread underneath went on saying "Topic
 * Discovery is up next — tell me the broad area you want to study" next to a
 * live composer, on a job whose entire premise is that nobody types anything;
 * and the run itself — the thing the student is paying for and waiting on —
 * was a side panel with a monospace event log.
 *
 * So the run IS the screen. Six modules as steps, the live line under the one
 * that's working, and the controls that actually apply (pause / stop / resume).
 * When it finishes the same screen becomes the payoff: the exports, the
 * editor, and an explicit door into chat for anyone who wants changes.
 *
 * Presentational apart from its own run polling: the parent owns whether this
 * shows at all, and owns the way back to chat.
 */

const MODULES = ["M1", "M2", "M3", "M4", "M5"] as const;

type RunRow = {
  id?: string;
  status?: string;
  phase?: string | null;
  started_at?: string | null;
  error_text?: string | null;
};

type ModuleStatusMap = Partial<Record<(typeof MODULES)[number], string>>;

function walkTo(byModule: Record<string, ModuleStatus>, phase: string) {
  // Auto Thesis walks M1→M5. Everything before `phase` is finished; `phase`
  // itself is the one working. Used for both the live SSE `phase_progress`
  // event and the Job row's `phase` column (same value, durable across reload).
  const idx = MODULES.indexOf(phase as (typeof MODULES)[number]);
  if (idx < 0) return;
  for (let i = 0; i < idx; i++) byModule[MODULES[i]] = "done";
  if (byModule[phase] !== "done") byModule[phase] = "active";
}

export function AutoThesisRunView({
  runId,
  projectId,
  topic,
  initialStatus,
  moduleStatus,
  onRetry,
  onAskInChat,
}: {
  runId: string;
  projectId: string;
  /** The thesis being written. Empty is tolerated — the run still shows. */
  topic?: string;
  /** Status the parent already knows (from /runs/list). Without this the
   *  child's own fetch defaults the screen to "queued"/"Starting…" on every
   *  reload, for a run that has been going for minutes. */
  initialStatus?: string | null;
  /** Committed project.module_status — another reload snapshot. The run
   *  writes this as it goes, so a refresh can restore ticks before SSE
   *  replays. */
  moduleStatus?: ModuleStatusMap;
  /** Resume a failed/canceled run from its last committed module. */
  onRetry?: () => void;
  /** Leave the run screen for the thread. The parent decides what that means. */
  onAskInChat: () => void;
}) {
  const t = useT();
  const { data: run, mutate: mutateRun } = useSWR<RunRow>(
    `/runs/${runId}`, fetcher, {
      refreshInterval: 5000,
      // Don't flash "Starting…" over a run the parent already knows is live.
      fallbackData: initialStatus
        ? { id: runId, status: initialStatus }
        : undefined,
    },
  );
  const { events } = useAutoThesisRun(runId);

  // `job_done` arrives on the stream the moment the run finishes; the row this
  // polls catches up on its own 5s cycle. Waiting for the poll left the screen
  // saying "Writing your thesis" — spinner and all — over a thesis that was
  // already written and whose download links were sitting in the event. The
  // stream only ever promotes a run that is still reported as in-flight; a
  // terminal status from the server (failed, canceled) is the server's to own.
  const jobDone = useMemo(() => events.some(e => e.type === "job_done"), [events]);
  const reported = run?.status ?? initialStatus ?? "queued";
  const status = jobDone && (reported === "queued" || reported === "running")
    ? "done" : reported;
  const live = status === "queued" || status === "running" || status === "paused";

  // Module checklist. Two signals, because they disagree on a finished run:
  //
  //   events — what the runner actually writes. Headless emits
  //            `phase_progress` (focus module) and `activity` (often with no
  //            `module` field). It never emits `module_complete`, which is
  //            why a 22-minute finished thesis used to sit on LOCKED under
  //            "Your thesis is ready".
  //   status — the Job row. `done` means every required module committed;
  //            the checklist has to match the headline, even if the stream
  //            was empty (poll caught up, events didn't).
  const { statusByModule, detailByModule } = useMemo(() => {
    const byModule: Record<string, ModuleStatus> = {
      M1: "locked", M2: "locked", M3: "locked", M4: "locked", M5: "locked",
    };
    const detail: Record<string, string> = {};
    let current: string | null = null;

    const asModule = (ev: { module?: unknown; phase?: unknown }) => {
      const m = (typeof ev.module === "string" && ev.module)
        || (typeof ev.phase === "string" && ev.phase)
        || null;
      return m && m in byModule ? m : null;
    };

    // 1. Project store — what commit_slice has already written. Survives a
    //    refresh even when the event stream hasn't replayed yet.
    for (const id of MODULES) {
      const s = moduleStatus?.[id];
      if (s === "done") byModule[id] = "done";
      else if (s === "in_progress") byModule[id] = "active";
    }

    // 2. Job.phase — the monitor copies this off every phase_progress beat,
    //    so the row itself is a snapshot of "where the run is".
    if (run?.phase) walkTo(byModule, run.phase);

    for (const ev of events) {
      if (ev.type === "phase_progress") {
        const m = asModule(ev);
        if (!m) continue;
        walkTo(byModule, m);
        current = m;
      } else if (ev.type === "module_complete") {
        const m = asModule(ev);
        if (!m) continue;
        byModule[m] = "done";
        delete detail[m];
      } else if (ev.type === "activity") {
        const m = asModule(ev) || current || (run?.phase && run.phase in byModule ? run.phase : null);
        if (!m) continue;
        if (byModule[m] !== "done") byModule[m] = "active";
        const text = (ev as { text?: string }).text;
        if (text) detail[m] = text;
      }
    }

    if (status === "done") {
      for (const id of MODULES) {
        byModule[id] = "done";
        delete detail[id];
      }
    }
    return { statusByModule: byModule, detailByModule: detail };
  }, [events, status, run?.phase, moduleStatus]);

  const tokens = events
    .filter(e => e.type === "token_cost")
    .reduce((acc, e) => acc + ((e as { tokens?: number }).tokens ?? 0), 0);
  const exports = (events.find(e => e.type === "job_done") as
    { exports?: Record<string, string> } | undefined)?.exports;

  // Elapsed, not "time remaining". Nothing in the system predicts how long a
  // thesis takes, and a countdown the run can't honour is worse than no number.
  const minutes = run?.started_at
    ? Math.max(0, Math.round((Date.now() - new Date(run.started_at).getTime()) / 60000))
    : null;

  const control = async (action: "pause" | "resume" | "cancel") => {
    await apiFetch(`/runs/${runId}/${action}`, { method: "POST" }).catch(() => null);
    void mutateRun();
  };

  const headline: MessageKey =
    status === "done" ? "run.done.title"
      : status === "failed" ? "run.failed.title"
        : status === "canceled" ? "run.canceled.title"
          : "run.live.title";
  const body: MessageKey =
    status === "done" ? "run.done.body"
      : status === "failed" || status === "canceled" ? "run.stopped.body"
        : "run.live.body";

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10">
      <div className="mx-auto w-full max-w-xl">
        <p className="m-0 text-[11px] uppercase tracking-[0.08em] font-bold text-primary-600">
          {t("run.eyebrow")}
        </p>
        <h2 className="mt-2 mb-0 text-[22px] font-extrabold font-serif tracking-tight text-ink-900 flex items-center gap-2">
          {live && status !== "paused" && (
            <Loader2 className="w-4 h-4 animate-spin text-primary-600 shrink-0" aria-hidden />
          )}
          {t(headline)}
        </h2>
        {topic && (
          <p className="mt-1.5 mb-0 text-[13.5px] text-ink-600 leading-relaxed">“{topic}”</p>
        )}
        {/* The one sentence this screen exists to say: nothing is waiting on
            you. Without it a student watches a progress list and assumes the
            silence means they were supposed to answer something. */}
        <p className="mt-3 mb-0 text-[13px] text-ink-500 leading-relaxed">{t(body)}</p>

        {status === "failed" && run?.error_text && (
          <p className="mt-3 mb-0 text-[12.5px] text-red-700">{run.error_text}</p>
        )}

        <div className="mt-7">
          {MODULES.map((m, i) => (
            <ModuleProgressDot
              key={m}
              module={m}
              label={t(`module.${m}` as MessageKey)}
              status={statusByModule[m]}
              detail={detailByModule[m]}
              isLast={i === MODULES.length - 1}
            />
          ))}
        </div>

        <p className="mt-5 mb-0 text-[12px] text-ink-400">
          {status === "queued"
            ? t("run.queued")
            : [
              minutes !== null ? t("run.elapsed", { n: String(minutes) }) : null,
              tokens > 0 ? t("run.tokens", { n: tokens.toLocaleString() }) : null,
            ].filter(Boolean).join(" · ")}
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-2.5">
          {status === "running" && (
            <button type="button" onClick={() => void control("pause")} className={SECONDARY}>
              <Pause className="w-3.5 h-3.5" /> {t("run.pause")}
            </button>
          )}
          {status === "paused" && (
            <button type="button" onClick={() => void control("resume")} className={PRIMARY}>
              <Play className="w-3.5 h-3.5" /> {t("run.resume")}
            </button>
          )}
          {live && (
            <button type="button" onClick={() => void control("cancel")} className={DANGER}>
              <XCircle className="w-3.5 h-3.5" /> {t("run.stop")}
            </button>
          )}
          {(status === "failed" || status === "canceled") && onRetry && (
            <button type="button" onClick={onRetry} className={PRIMARY}>
              <RotateCcw className="w-3.5 h-3.5" /> {t("run.retry")}
            </button>
          )}
          {status === "done" && (
            <Link href={`/chat/projects/${projectId}/editor`} className={PRIMARY}>
              {t("run.openEditor")}
            </Link>
          )}
          {status === "done" && exports && Object.entries(exports).map(([kind, uri]) => (
            <ExportButton key={kind} kind={kind} uri={uri} />
          ))}
        </div>

        {/* Always available, never the loud option: a run in flight can still
            be asked about, and a finished one usually wants changes. */}
        <button
          type="button"
          onClick={onAskInChat}
          className="mt-5 text-[12.5px] font-semibold text-primary-600 hover:text-primary-700 hover:underline"
        >
          {t(status === "done" ? "run.askChanges" : "run.askInChat")}
        </button>
      </div>
    </div>
  );
}

const PRIMARY =
  "inline-flex items-center gap-1.5 rounded-full bg-primary-600 px-4 py-2 text-[13px] " +
  "font-bold text-white no-underline hover:bg-primary-700 transition-colors";
const SECONDARY =
  "inline-flex items-center gap-1.5 rounded-full border border-ink-200 bg-white px-3.5 py-2 " +
  "text-[13px] font-semibold text-ink-700 hover:bg-ink-50 transition-colors";
const DANGER =
  "inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[13px] font-semibold " +
  "text-red-700 hover:bg-red-50 transition-colors";


// The export mints a scoped token before the browser sees a URL, so the click
// has a round trip in it. Without the busy state the button looks dead.
function ExportButton({ kind, uri }: { kind: string; uri: string }) {
  const t = useT();
  const { busy, error, start } = useArtifactDownload();
  return (
    <>
      <button
        type="button"
        aria-busy={busy}
        onClick={() => void start(() => triggerExportDownload(uri))}
        className={SECONDARY}
      >
        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />}
        {t("run.download", { kind: kind.toUpperCase() })}
      </button>
      {error && <span className="text-[11.5px] text-[#8E6B2A]" role="alert">{error}</span>}
    </>
  );
}
