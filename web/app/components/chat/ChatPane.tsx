"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Zap } from "lucide-react";
import useSWR from "swr";
import { useChat } from "./hooks/useChat";
import { useMe } from "@/app/lib/use-me";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AutoDraftButton, type RunStatus } from "./AutoDraftButton";
import { AutoDraftModal } from "./AutoDraftModal";
import { AutoDraftDrawer } from "./AutoDraftDrawer";
import { synthesizeWidgetSelection } from "./widgets/synthesize";
import type { WidgetSelectHandler } from "./widgets/types";
import {
  formatAnalyzeMessage,
  readAnalyzeIntent,
  type AnalyzeKind,
} from "@/app/lib/bootstrap-payload";
import { AnalysisOverlay } from "./AnalysisOverlay";
import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";


/**
 * Empty-state copy for a thread with no messages yet.
 *
 * The text used to be "Start your thesis" no matter what — that read as
 * a regression to users who had already finished M1/M2 in a previous
 * thread (the project state is shared across threads). We now base the
 * copy on what's actually in context_store + module_status, so a new
 * thread on a partly-complete project picks up where the project is.
 *
 * Precedence:
 *   1. ANY module marked `needs_review` → invite the user to fix the
 *      flagged module first (that's the most urgent signal in the brief).
 *   2. M5 has chapters → handled by the caller (the auto-drafted branch
 *      above this; we never reach `getEmptyStateCopy` in that case).
 *   3. Otherwise: greet by the "current focus" module — what's the user
 *      working on right now — and remind them what its job is.
 *   4. Cold start (no committed slices anywhere) → original "Start your
 *      thesis" copy.
 */
function getEmptyStateCopy(project: {
  context_store: {
    m1_topic?: { research_title?: string; confirmed_at?: string } | null;
    m2_literature?: { confirmed_at?: string } | null;
    m3_design?: { confirmed_at?: string } | null;
    m4_analysis?: { confirmed_at?: string } | null;
    m5_writing?: { confirmed_at?: string } | null;
  };
  focus?: string | null;
  current_module?: string;
  module_status?: Record<string, string>;
}): { title: string; body: string } {
  const cs = project.context_store;
  const status = project.module_status ?? {};
  const focus = project.focus ?? project.current_module;
  const title = cs.m1_topic?.research_title;

  // 1. Needs-review beats everything — surface the worst.
  const flagged = ["M1", "M2", "M3", "M4", "M5"].find(m => status[m] === "needs_review");
  if (flagged) {
    return {
      title: `${flagged} needs another look`,
      body:
        `Something in ${MODULE_LABEL[flagged]} changed upstream — let's revisit it so the rest stays grounded.` +
        (title ? ` (Project: ${title})` : ""),
    };
  }

  // 2. The auto-drafted branch is handled above by the caller. We can't
  //    reach this point with `hasChapters === true`.

  // 3. Welcome back, based on where the user is.
  const m1Done = !!cs.m1_topic?.confirmed_at || !!title;
  const m2Done = !!cs.m2_literature?.confirmed_at;
  const m3Done = !!cs.m3_design?.confirmed_at;
  const m4Done = !!cs.m4_analysis?.confirmed_at;
  if (m1Done || m2Done || m3Done || m4Done) {
    // Pick the first module that isn't done — that's the next step.
    const nextModule = !m1Done ? "M1"
      : !m2Done ? "M2"
      : !m3Done ? "M3"
      : !m4Done ? "M4"
      : "M5";
    const focusedOn = focus && status[focus] !== "done" ? focus : nextModule;
    return {
      title: title
        ? `Picking up "${title}"`
        : `Continuing your thesis`,
      body:
        `${MODULE_LABEL[focusedOn]} is up next — ${MODULE_HINT[focusedOn]} ` +
        `Type below to dive in, or ask about any module.`,
    };
  }

  // 4. Cold start.
  return {
    title: "Start your thesis",
    body:
      "Type your research topic below and I'll guide you step by step — " +
      "or hit Auto approve to write the full thesis end-to-end.",
  };
}

const MODULE_LABEL: Record<string, string> = {
  M1: "Topic Discovery",
  M2: "Literature Review",
  M3: "Research Design",
  M4: "Data Analysis",
  M5: "Writing",
};

const MODULE_HINT: Record<string, string> = {
  M1: "tell me the broad area you want to study.",
  M2: "let's map the literature and find the gaps your hypotheses will plug.",
  M3: "time to pick the paradigm, design, and instrument.",
  M4: "ready to crunch the data once you have it.",
  M5: "let's turn the project into chapters and export.",
};


export function ChatPane({ projectId, threadId }: { projectId: string; threadId: string }) {
  const { messages, streamingText, streamingProgress, streamingError, inflight, send } = useChat(threadId);

  // Credit balance drives the out-of-credits CTA. Default to >0 while loading so
  // the upgrade banner doesn't flash for paying users on first paint. The
  // backend gates turns at <= 0 (chat.py send_message → 402 insufficient_credit);
  // this is the matching UI so the user sees WHY a turn won't run + how to fix it.
  const { data: me } = useMe();
  const outOfCredits = me != null && (me.credit ?? 0) <= 0;

  // Warn before closing/reloading the tab while a turn is streaming. A reload
  // abandons the in-flight answer — the server stops the agent and saves only
  // the partial reply — so prompt the user to confirm they want to lose it.
  useEffect(() => {
    if (!inflight) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // Chrome requires returnValue set to show the prompt.
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [inflight]);
  // SP6.5: include m5_writing.chapters so we can gate the "Open editor" link in
  // ChatHeader — the link must only appear once at least one chapter exists.
  // focus/current_module/module_status drive the header's focus chip (design's
  // focus bar: "M2 · Literature Review · In progress").
  const { data: project, mutate: mutateProject } = useSWR<{
    name: string;
    focus?: string | null;
    current_module?: string;
    module_status?: Record<string, string>;
    // Each slice optional; presence + confirmed_at drives the empty-state
    // copy below. The shapes are loose on purpose — we only read a few
    // fields and want to tolerate dual-write / partial data.
    context_store: {
      m1_topic?: { research_title?: string; confirmed_at?: string } | null;
      m2_literature?: { research_state_summary?: string; confirmed_at?: string } | null;
      m3_design?: { methodology?: { paradigm?: string }; confirmed_at?: string } | null;
      m4_analysis?: { confirmed_at?: string } | null;
      m5_writing?: {
        chapters?: Record<string, unknown>;
        // Conversational/export path stores prose here instead of `chapters`;
        // the editor backfills chapters from it (api/app/routers/m5_editor.py).
        final_sections?: unknown[];
        confirmed_at?: string;
        // M5 auto-export hook (api/app/agent_state.py:_auto_export_m5)
        // writes these on the M5 done transition. ChatHeader Download
        // button + ContextPanel M5 card both read from here.
        export_artifacts?: { kind: string; download_url: string }[];
      } | null;
    };
  }>(
    `/projects/${projectId}`, fetcher,
  );

  // Suggested actions for an EMPTY thread. Same POST /projects/{id}/roadmap the
  // right panel uses, so the chips in both places are always the same advice —
  // a second, locally-derived "what next" would drift the moment either changed.
  //
  // Gated on `messages.length === 0`: the roadmap is only rendered by the empty
  // state, so fetching it on every populated thread would be a request per chat
  // open for markup nobody sees. SWR's null key skips the call entirely.
  const { data: roadmap } = useSWR<{
    next_action?: { title?: string; cta_options?: string[] } | Record<string, never>;
  }>(
    messages.length === 0 ? `/projects/${projectId}/roadmap` : null,
    (url: string) => apiFetch(url, { method: "POST" }),
  );
  const emptyStateNextAction =
    roadmap?.next_action && "title" in roadmap.next_action
      ? (roadmap.next_action as { title: string; cta_options?: string[] })
      : null;
  // threadError matters on its own: the project can load fine while the thread
  // itself is gone (stale bookmark, deleted thread). Without it the pane
  // rendered a normal-looking chat with a live composer pointed at a thread id
  // the API 404s on — every send would fail with nothing on screen to explain it.
  const { data: thread, error: threadError } = useSWR<{ name: string }>(
    `/threads/${threadId}`, fetcher,
  );
  const { data: latestRun, mutate: mutateRun } = useSWR<{ run: { id: string; status: RunStatus } | null }>(
    `/projects/${projectId}/runs/list?latest=true`, fetcher,
  );

  // Analyze-intent pickup. The drop-first /new page stashes the dropped files
  // (already uploaded) + an optional note keyed by project id, then routes here
  // with ?analyzing=1. The first time this thread mounts empty, we fire ONE
  // bootstrap turn that reads the uploads and reports where the thesis stands,
  // shown as a dedicated analysis screen (AnalysisOverlay) on top of the chat
  // until the user hits Continue. Guarded by a ref so StrictMode's double-mount
  // in dev doesn't fire twice. The turn persists an assistant Message, so on any
  // later mount `messages.length > 0` and we never re-run it.
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzePhase, setAnalyzePhase] = useState<"running" | "done" | "failed">("running");
  const analyzeFiredRef = useRef(false);
  // Kept so "Try again" can re-run the same turn after the stash is consumed.
  // `kind` rides along so "Try again" re-runs the SAME job — re-firing a
  // humanize request as a plain assessment would silently change what the
  // retry does.
  const analyzeIntentRef = useRef<
    { note: string; attachments: any[]; kind?: AnalyzeKind; preseeded?: boolean } | null
  >(null);

  const runAnalyze = useCallback(async () => {
    const intent = analyzeIntentRef.current;
    if (!intent) return;
    // AnalysisOverlay is the assessment screen — module dots, "here's where you
    // stand". A humanize turn seeds no module state on purpose, so it must not
    // be judged by that screen: the success check below reads module_status,
    // which would be empty, and every successful rewrite would render as
    // "failed". The chat transcript IS the result for a rewrite, so let it
    // stream normally instead of covering it with an overlay about something
    // else.
    const isHumanize = (intent.kind ?? "assess") === "humanize";
    // A preseeded turn is the student's own request against a project whose
    // modules are already committed — not an assessment. Covering it with the
    // "here's where you stand" overlay would hide the answer they asked for
    // behind a screen repeating the import card they just left.
    const skipOverlay = isHumanize || !!intent.preseeded;
    if (!skipOverlay) {
      setAnalyzing(true);
      setAnalyzePhase("running");
    }
    const msg = formatAnalyzeMessage(
      intent.note, intent.attachments.length > 0, intent.kind ?? "assess",
      !!intent.preseeded,
    );
    // send resolves when the turn's SSE stream closes. await the project
    // refetch (not fire-and-forget) so the result phase reads the freshly-
    // committed module_status rather than the stale pre-turn snapshot.
    await send(msg, undefined, intent.attachments);
    const fresh = await mutateProject();
    if (skipOverlay) return;  // no overlay to resolve
    // A turn that was killed/aborted before commit_slice (e.g. server restart,
    // disconnect) leaves every module "locked"/absent. Don't present that as a
    // finished analysis — surface a retry instead of a misleading "all not
    // started" screen.
    const ms = fresh?.module_status ?? {};
    const committed = Object.values(ms).some(s => s && s !== "locked");
    setAnalyzePhase(committed ? "done" : "failed");
  }, [send, mutateProject]);

  useEffect(() => {
    if (analyzeFiredRef.current) return;
    if (messages.length > 0 || inflight) return;
    const intent = readAnalyzeIntent(projectId);
    if (!intent) return;
    analyzeFiredRef.current = true;
    analyzeIntentRef.current = intent;
    void runAnalyze();
  }, [projectId, messages.length, inflight, runAnalyze]);

  // The editor entry point ("Open editor" / "Read your draft") should appear as
  // soon as there's an editable thesis — which is true via ANY of: drafted
  // `chapters`, conversational `final_sections` (the editor backfills chapters
  // from these), or a generated DOCX export. Gating only on `chapters` hid the
  // editor for projects whose M5 went through the final_sections/export path
  // even though a finished DOCX existed. Defaults false while loading.
  const _m5 = project?.context_store?.m5_writing;
  const hasChapters =
    Object.keys(_m5?.chapters ?? {}).length > 0 ||
    (_m5?.final_sections?.length ?? 0) > 0 ||
    (_m5?.export_artifacts?.some(a => a.kind === "docx") ?? false);

  // "Ready to draft" = the upstream research modules (M1–M4) are all done
  // and no auto-draft run has started yet. This is the moment the user
  // should reach for Auto-draft instead of asking chat to "write the whole
  // thesis" — so we light the button up. M5 itself is excluded: it's the
  // module Auto-draft produces, so requiring it done would never trigger.
  const upstreamDone =
    !!project?.module_status &&
    ["M1", "M2", "M3", "M4"].every(m => project.module_status?.[m] === "done");
  const autoDraftReady = upstreamDone && (latestRun?.run?.status ?? null) === null;

  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Bumped on resume to remount the drawer so its SSE stream reconnects to the
  // freshly re-spawned run (the previous stream closed on the terminal event).
  const [runNonce, setRunNonce] = useState(0);

  const onAutoDraftClick = () => {
    const status = latestRun?.run?.status ?? null;
    // If a run is active/done/failed, open the drawer to show its progress
    if (status === "running" || status === "paused" || status === "done" || status === "failed") {
      setDrawerOpen(true);
    } else {
      setModalOpen(true);
    }
  };

  const confirmAutoDraft = async (topic: string) => {
    setModalOpen(false);
    try {
      await apiFetch(`/projects/${projectId}/runs`, {
        method: "POST",
        body: { mode: "auto", topic },
      });
      void mutateRun();
      setDrawerOpen(true);
    } catch {
      // Errors surface elsewhere; we just don't open the drawer.
    }
  };

  // Retry a failed/canceled run by RESUMING its checkpoint (re-runs the module
  // that died, keeping the completed ones) rather than starting over from M1.
  // If resume isn't possible, fall back to the fresh-run modal.
  const resumeRun = async () => {
    const run = latestRun?.run;
    if (!run) { setModalOpen(true); return; }
    try {
      await apiFetch(`/runs/${run.id}/resume`, { method: "POST" });
      void mutateRun();
      setRunNonce(n => n + 1);
    } catch {
      setDrawerOpen(false);
      setModalOpen(true);
    }
  };

  const onWidgetSelect: WidgetSelectHandler = (fieldName, value, label) => {
    // SP3: translate widget click into a natural-language user message that
    // the agent's free-text extractor can parse. Click thus reuses the
    // existing send path — no new backend protocol needed.
    const text = synthesizeWidgetSelection(fieldName, value, label);

    // Rich widgets (FlowChart, ListEditor) emit JSON in `value`. Forward it
    // as a structured payload so the backend uses it verbatim instead of
    // round-tripping through LLM text-extraction (which silently dropped
    // nested shapes like M3's {nodes:[{label,questions}],edges:[]} down to
    // {paths:[...]}). CardGrid sends bare strings — those parse as JSON
    // primitives and we don't want to bypass the prose path for them.
    let widgetPayload: { field_name: string; value: unknown } | undefined;
    if (value.trim().startsWith("{") || value.trim().startsWith("[")) {
      try {
        widgetPayload = { field_name: fieldName, value: JSON.parse(value) };
      } catch {
        // Malformed JSON — fall back to prose-only send.
      }
    }
    void send(text, widgetPayload);
  };

  const onFileDrop = async (files: File[]): Promise<(string | null)[]> => {
    // FormData uploads can't go through apiFetch (which JSON-encodes the
    // body), and a multipart request has no JSON body to carry the token —
    // so we pass it in an Authorization: Bearer header instead of the URL.
    // Keeping the token out of the URL avoids leaking the JWT into access
    // logs / referrers; the uploads endpoint reads the Bearer header via
    // the body/query/Bearer fallback (see api/app/deps.py:_extract_token).
    // Returns the per-file `upload_id` (or null on failure) in input order
    // so ChatInput can stamp each chip + ship the ids on Send. Without
    // these ids the chat router can't materialize the bytes for Gemini.
    const token = tokenStore.get();
    const base = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
    const results = await Promise.all(files.map(async (f): Promise<string | null> => {
      try {
        const fd = new FormData();
        fd.append("file", f);
        const res = await fetch(`${base}/projects/${projectId}/uploads`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: fd,
        });
        if (!res.ok) return null;
        const body = await res.json();
        return (body?.upload_id as string) ?? null;
      } catch {
        return null;
      }
    }));
    return results;
  };

  // Placed after every hook so the early return can't change hook order.
  if (threadError) {
    const status = (threadError as { status?: number })?.status;
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <p className="text-lg font-semibold text-ink-800 m-0">
          {status === 404 ? "This thread no longer exists" : "Couldn’t load this thread"}
        </p>
        <p className="mt-1.5 text-sm text-ink-500 max-w-md">
          {status === 404
            ? "It was deleted, or the link is out of date. Pick another thread from the left rail."
            : (threadError as Error)?.message || "Try again in a moment."}
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center px-4 py-2 rounded-full text-[13.5px] font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      {analyzing && (
        <AnalysisOverlay
          phase={analyzePhase}
          progress={analyzePhase === "running" ? streamingProgress : []}
          moduleStatus={project?.module_status ?? {}}
          focus={project?.focus ?? project?.current_module}
          projectTitle={project?.name}
          onContinue={() => setAnalyzing(false)}
          onRetry={() => void runAnalyze()}
          outOfCredits={outOfCredits}
        />
      )}
      <ChatHeader
        projectName={project?.name ?? ""}
        threadName={thread?.name ?? ""}
        loading={!project}
        focusModule={project ? (project.focus ?? project.current_module) : undefined}
        focusStatus={
          project
            ? project.module_status?.[project.focus ?? project.current_module ?? ""] ?? "in_progress"
            : undefined
        }
        autoDraftButton={
          <AutoDraftButton
            runStatus={latestRun?.run?.status ?? null}
            onClick={onAutoDraftClick}
            ready={autoDraftReady}
          />
        }
        projectId={projectId}
        hasChapters={hasChapters}
        exportArtifacts={project?.context_store?.m5_writing?.export_artifacts}
        // Export-to-Word quick actions → agent prompt (export_docx scope=Mx),
        // which files the export under its module scope, not M5.
        onQuickPrompt={(t) => void send(t)}
      />
      {!project ? (
        // Until the project lands this rendered the message list — which is
        // empty at that point — so opening a thread showed a blank pane under a
        // header of placeholder punctuation, indistinguishable from a thread
        // that failed to load. Show that something is coming instead.
        <div className="flex-1 px-6 py-7 flex flex-col gap-6 max-w-3xl w-full mx-auto"
             aria-busy="true" aria-label="Loading conversation">
          {/* Bubble-shaped, so the pane reads as a conversation arriving rather
              than as loose bars. The assistant side is wider and left-aligned,
              the user side narrower and right-aligned, matching the real
              MessageBubble rhythm. */}
          {[
            { mine: false, lines: ["w-11/12", "w-4/5"] },
            { mine: true, lines: ["w-3/4"] },
            { mine: false, lines: ["w-full", "w-10/12", "w-7/12"] },
          ].map((row, i) => (
            <div key={i} className={row.mine ? "self-end max-w-[70%]" : "self-start max-w-[85%]"}>
              <div
                className={`rounded-2xl px-4 py-3 flex flex-col gap-2 ${
                  row.mine ? "bg-ink-100/70" : "bg-ink-50 border border-ink-200/70"
                }`}
              >
                {row.lines.map((w, j) => (
                  <span key={j} className={`h-2.5 rounded-full bg-ink-200/80 animate-pulse ${w}`} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : messages.length === 0 && !inflight ? (
        // An empty thread is confusing — especially for an auto-drafted project,
        // where all the content lives in the editor + progress panel, not in chat.
        // Point the user to the right place instead of showing a blank pane.
        <div className="flex-1 flex flex-col items-center justify-center text-center px-6 text-ink-500">
          {hasChapters ? (
            <>
              <p className="text-lg font-semibold text-ink-800">This thesis was auto-written</p>
              <p className="mt-1 text-sm max-w-md">
                All modules are complete — the draft lives in the editor and the
                progress panel. Open the editor to read it, or type below to
                refine any section.
              </p>
              {/* Distinct label from the header's "Open editor" button — two
                  identically-named links to the same target read as a bug to
                  screen readers (and broke the getByRole query in tests). */}
              <a
                href={`/chat/projects/${projectId}/editor`}
                className="mt-4 inline-flex items-center gap-2 py-2 px-5 bg-primary-600 text-white text-sm font-semibold rounded-full hover:bg-primary-700 transition-colors"
              >
                Read your draft →
              </a>
            </>
          ) : (
            (() => {
              const copy = getEmptyStateCopy(project);
              const na = emptyStateNextAction;
              return (
                <>
                  <p className="text-lg font-semibold text-ink-800">{copy.title}</p>
                  <p className="mt-1 text-sm max-w-md">{copy.body}</p>
                  {/* An empty thread used to offer nothing but a blank box, even
                      though the roadmap already knows exactly what to do next —
                      next_action() returns a title AND cta_options, and the
                      right panel has rendered them for ages. Landing a student
                      on "type something" when the system can say "confirm M1 is
                      done" is a needless dead end. Same data source as the
                      panel, so the two can't drift. */}
                  {na?.cta_options?.length ? (
                    <div className="mt-5 flex flex-col items-center gap-2">
                      <p className="text-[12px] uppercase tracking-[0.08em] text-ink-400 font-semibold">
                        {na.title}
                      </p>
                      <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                        {na.cta_options.map((c) => (
                          <button
                            key={c}
                            type="button"
                            onClick={() => void send(c)}
                            className="rounded-full border border-primary-200 bg-primary-50 px-3.5 py-1.5 text-[13px] font-semibold text-primary-700 hover:bg-primary-100 hover:border-primary-400 transition-colors"
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </>
              );
            })()
          )}
        </div>
      ) : (
        <MessageList
          messages={messages}
          streamingText={inflight ? streamingText : ""}
          streamingModuleTag={null}
          streamingProgress={inflight ? streamingProgress : []}
          streamingError={streamingError}
          inflight={inflight}
          onWidgetSelect={onWidgetSelect}
          projectId={projectId}
        />
      )}
      {outOfCredits && (
        <div className="mx-auto mb-2 flex w-full max-w-3xl items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <Zap className="h-4 w-4 shrink-0 text-amber-600" />
          <div className="flex-1 text-[13px] leading-snug text-amber-900">
            <span className="font-semibold">You're out of credits.</span>{" "}
            Top up to keep analyzing your thesis and chatting.
          </div>
          <Link
            href="/credit"
            className="shrink-0 rounded-lg bg-amber-600 px-3.5 py-1.5 text-[13px] font-semibold text-white no-underline hover:bg-amber-700"
          >
            Upgrade credits
          </Link>
        </div>
      )}
      <ChatInput
        // ChatInput emits (text, attachments[]) — send's signature is
        // (text, widgetPayload, attachments). Skip the widgetPayload slot
        // for composer sends; that slot is only for widget-click
        // translations routed through onWidgetSelect above. We forward
        // the FULL chip metadata (not just upload_ids) so the optimistic
        // user bubble can render the linked-file chips on the spot —
        // without waiting for SWR to revalidate the server row.
        onSubmit={(text, attachments) => void send(text, undefined, attachments)}
        onFileDrop={onFileDrop}
        // Disable the composer when out of credits — the backend would 402 the
        // turn anyway; blocking here avoids an orphaned user message + a confusing
        // no-reply, and points the user at the upgrade CTA above instead.
        disabled={inflight || outOfCredits}
        focusModule={project ? (project.focus ?? project.current_module) : undefined}
      />

      <AutoDraftModal
        open={modalOpen}
        projectId={projectId}
        defaultTopic={project?.context_store?.m1_topic?.research_title ?? ""}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmAutoDraft}
      />
      {drawerOpen && latestRun?.run && (
        <AutoDraftDrawer
          key={`${latestRun.run.id}:${runNonce}`}
          runId={latestRun.run.id}
          onClose={() => setDrawerOpen(false)}
          // Retry a failed/canceled run = resume from its last checkpoint.
          onRetry={resumeRun}
        />
      )}
    </>
  );
}
