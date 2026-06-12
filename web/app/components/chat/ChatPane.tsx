"use client";

import { useState } from "react";
import useSWR from "swr";
import { useChat } from "./hooks/useChat";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AutoDraftButton, type RunStatus } from "./AutoDraftButton";
import { AutoDraftModal } from "./AutoDraftModal";
import { AutoDraftDrawer } from "./AutoDraftDrawer";
import { synthesizeWidgetSelection } from "./widgets/synthesize";
import type { WidgetSelectHandler } from "./widgets/types";
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
      "or hit Auto-draft to generate a full draft.",
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
  // SP6.5: include m5_writing.chapters so we can gate the "Open editor" link in
  // ChatHeader — the link must only appear once at least one chapter exists.
  // focus/current_module/module_status drive the header's focus chip (design's
  // focus bar: "M2 · Literature Review · In progress").
  const { data: project } = useSWR<{
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
      m5_writing?: { chapters?: Record<string, unknown>; confirmed_at?: string } | null;
    };
  }>(
    `/projects/${projectId}`, fetcher,
  );
  const { data: thread } = useSWR<{ name: string }>(`/threads/${threadId}`, fetcher);
  const { data: latestRun, mutate: mutateRun } = useSWR<{ run: { id: string; status: RunStatus } | null }>(
    `/projects/${projectId}/runs?latest=true`, fetcher,
  );

  // SP6.5: gate is true only when at least one chapter entry exists.
  // Defaults to false while the project data is still loading.
  const hasChapters =
    Object.keys(project?.context_store?.m5_writing?.chapters ?? {}).length > 0;

  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  const onFileDrop = async (files: File[]) => {
    // FormData uploads can't go through apiFetch (which JSON-encodes the
    // body). Inject the token as a query string parameter so the request
    // still authenticates — uploads endpoint accepts auth via the same
    // body/query/Bearer fallback (see api/app/deps.py:_extract_token).
    const token = tokenStore.get();
    const tokenParam = token ? `?access_token=${encodeURIComponent(token)}` : "";
    const base = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      await fetch(`${base}/projects/${projectId}/uploads${tokenParam}`, {
        method: "POST",
        body: fd,
      });
    }
  };

  return (
    <>
      <ChatHeader
        projectName={project?.name ?? "…"}
        threadName={thread?.name ?? "…"}
        focusModule={project ? (project.focus ?? project.current_module) : undefined}
        focusStatus={
          project
            ? project.module_status?.[project.focus ?? project.current_module ?? ""] ?? "in_progress"
            : undefined
        }
        autoDraftButton={
          <AutoDraftButton runStatus={latestRun?.run?.status ?? null} onClick={onAutoDraftClick} />
        }
        projectId={projectId}
        hasChapters={hasChapters}
      />
      {project && messages.length === 0 && !inflight ? (
        // An empty thread is confusing — especially for an auto-drafted project,
        // where all the content lives in the editor + progress panel, not in chat.
        // Point the user to the right place instead of showing a blank pane.
        <div className="flex-1 flex flex-col items-center justify-center text-center px-6 text-gray-500">
          {hasChapters ? (
            <>
              <p className="text-lg font-semibold text-gray-800">✨ This thesis was auto-drafted</p>
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
              return (
                <>
                  <p className="text-lg font-semibold text-gray-800">{copy.title}</p>
                  <p className="mt-1 text-sm max-w-md">{copy.body}</p>
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
        />
      )}
      <ChatInput
        onSubmit={send}
        onFileDrop={onFileDrop}
        disabled={inflight}
        focusModule={project ? (project.focus ?? project.current_module) : undefined}
        // Hardcoded model label for now — matches what agent/runtime.py
        // actually loads. Pull from a real /api/v1/me/agent-config endpoint
        // when that lands so the user sees Claude vs Gemini accurately.
        modelName={process.env.NEXT_PUBLIC_AGENT_MODEL_LABEL || "Gemini 2.5 Flash"}
      />

      <AutoDraftModal
        open={modalOpen}
        projectId={projectId}
        defaultTopic={project?.context_store?.m1_topic?.research_title ?? ""}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmAutoDraft}
      />
      {drawerOpen && latestRun?.run && (
        <AutoDraftDrawer runId={latestRun.run.id} onClose={() => setDrawerOpen(false)} />
      )}
    </>
  );
}
