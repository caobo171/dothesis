"use client";

import Link from "next/link";
import { CheckCircle2, CircleDashed, Loader2, Lock, RotateCw, TriangleAlert, Zap } from "lucide-react";
import { Button } from "@/app/components/ui/button";

/**
 * Full-screen analysis screen shown on top of the chat surface while (and just
 * after) the drop-first onboarding's bootstrap turn runs. Two phases:
 *   - running: live progress beats ("Reading draft.pdf…") so the 30–90s
 *     bootstrap turn feels like work, not a hang.
 *   - done: the per-module M1–M5 coverage the bootstrap turn committed, plus
 *     the recommended entry focus, and a Continue button into the chat.
 *
 * It deliberately covers the chat until the user hits Continue — the user
 * asked for a dedicated "where you stand" screen BEFORE the workspace.
 */

const MODULES = ["M1", "M2", "M3", "M4", "M5"] as const;

const MODULE_LABEL: Record<string, string> = {
  M1: "Topic",
  M2: "Literature",
  M3: "Design",
  M4: "Data Analysis",
  // One writing step, not two: the discussion of findings is written INSIDE
  // the closing chapter rather than as a chapter of its own.
  M5: "Conclusion",
};

type StatusKey = "done" | "in_progress" | "locked" | "not_started";

const STATUS_META: Record<StatusKey, { label: string; icon: React.ReactNode; cls: string }> = {
  done:         { label: "done",         icon: <CheckCircle2 className="w-4 h-4" />,  cls: "text-green-700 bg-green-50 border-green-200" },
  in_progress:  { label: "in progress",  icon: <CircleDashed className="w-4 h-4" />,  cls: "text-primary-700 bg-primary-50 border-primary-200" },
  locked:       { label: "locked",       icon: <Lock className="w-4 h-4" />,          cls: "text-ink-500 bg-ink-50 border-ink-200" },
  not_started:  { label: "not started",  icon: <Lock className="w-4 h-4" />,          cls: "text-ink-500 bg-ink-50 border-ink-200" },
};

function statusKey(raw: string | undefined): StatusKey {
  // A legacy "needs_review" row reads as done — it always meant "was done,
  // then invalidated upstream", and invalidation no longer changes status.
  if (raw === "needs_review") return "done";
  if (raw === "done" || raw === "in_progress" || raw === "locked") return raw;
  return "not_started";
}

export function AnalysisOverlay({
  phase,
  progress,
  moduleStatus,
  focus,
  projectTitle,
  onContinue,
  onRetry,
  outOfCredits = false,
}: {
  phase: "running" | "done" | "failed";
  progress: { stage: string; message: string }[];
  moduleStatus: Record<string, string>;
  focus?: string | null;
  projectTitle?: string;
  onContinue: () => void;
  onRetry: () => void;
  outOfCredits?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-white/97 backdrop-blur-sm flex items-center justify-center px-6 overflow-y-auto">
      <div className="w-full max-w-lg py-10">
        {phase === "failed" ? (
          <div className="text-center">
            <span className="w-12 h-12 rounded-2xl inline-flex items-center justify-center mb-4 bg-amber-50 text-amber-600">
              {outOfCredits ? <Zap className="w-6 h-6" /> : <TriangleAlert className="w-6 h-6" />}
            </span>
            {outOfCredits ? (
              <>
                <h2 className="text-[20px] font-extrabold font-serif text-ink-900 m-0">
                  You're out of credits
                </h2>
                <p className="text-[13px] text-ink-500 mt-1.5 max-w-sm mx-auto">
                  Reading and analyzing your files needs credits. Your uploads are
                  saved — top up and we'll pick up right here.
                </p>
                <div className="flex flex-col gap-2 mt-6">
                  <Button asChild className="w-full">
                    <Link href="/credit">Upgrade credits</Link>
                  </Button>
                  <Button type="button" variant="ghost" onClick={onContinue} className="w-full">
                    Continue to workspace
                  </Button>
                </div>
              </>
            ) : (
              <>
                <h2 className="text-[20px] font-extrabold font-serif text-ink-900 m-0">
                  We couldn't finish reading your files
                </h2>
                <p className="text-[13px] text-ink-500 mt-1.5 max-w-sm mx-auto">
                  The analysis didn't complete, so nothing was saved yet. Your
                  uploads are still here — try again, or continue and tell me about
                  your thesis in chat.
                </p>
                <div className="flex flex-col gap-2 mt-6">
                  <Button type="button" onClick={onRetry} className="w-full">
                    <RotateCw className="w-4 h-4 mr-1.5" /> Try again
                  </Button>
                  <Button type="button" variant="ghost" onClick={onContinue} className="w-full">
                    Continue to workspace
                  </Button>
                </div>
              </>
            )}
          </div>
        ) : phase === "running" ? (
          <div className="text-center">
            <span className="w-12 h-12 rounded-2xl bg-primary-50 text-primary-600 inline-flex items-center justify-center mb-4">
              <Loader2 className="w-6 h-6 animate-spin" />
            </span>
            <h2 className="text-[20px] font-extrabold font-serif text-ink-900 m-0">
              Reading your files…
            </h2>
            <p className="text-[13px] text-ink-500 mt-1.5">
              Working out which parts of your thesis are already covered.
            </p>
            {progress.length > 0 && (
              <div className="mt-5 text-left flex flex-col gap-1.5">
                {progress.slice(-6).map((p, i) => (
                  <div key={i} className="flex items-start gap-2 text-[12.5px] text-ink-600">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-primary-400 shrink-0" />
                    <span>{p.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div>
            <div className="text-center mb-6">
              <h2 className="text-[22px] font-extrabold font-serif text-ink-900 m-0">
                Here's where your thesis stands
              </h2>
              {projectTitle && projectTitle !== "Untitled thesis" && (
                <p className="text-[13px] text-ink-500 mt-1.5">{projectTitle}</p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              {MODULES.map(m => {
                const meta = STATUS_META[statusKey(moduleStatus[m])];
                const isFocus = focus === m;
                return (
                  <div
                    key={m}
                    className={`flex items-center gap-3 px-4 py-3 rounded-2xl border ${
                      isFocus ? "border-primary-400 bg-primary-50/40" : "border-ink-200 bg-white"
                    }`}
                  >
                    <span className="text-[12px] font-bold text-ink-400 tabular-nums w-6">{m}</span>
                    <span className="flex-1 text-[14px] font-semibold text-ink-900">
                      {MODULE_LABEL[m]}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1.5 text-[12px] font-semibold px-2.5 py-1 rounded-full border ${meta.cls}`}
                    >
                      {meta.icon} {meta.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {focus && (
              <p className="text-[13px] text-ink-600 mt-5 text-center">
                <span className="font-semibold text-ink-900">Opening at {focus}</span> —{" "}
                {MODULE_LABEL[focus] ?? focus}. It's a recommendation, not a wall —
                jump anywhere from chat.
              </p>
            )}

            <Button type="button" onClick={onContinue} className="w-full mt-6">
              Continue to workspace
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
