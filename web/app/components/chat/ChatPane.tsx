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


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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
    context_store: {
      m1_topic?: { research_title?: string } | null;
      m5_writing?: { chapters?: Record<string, unknown> } | null;
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
    const r = await fetch(`/api/v1/projects/${projectId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "auto", topic }),
    });
    if (r.ok) {
      void mutateRun();
      setDrawerOpen(true);
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
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      await fetch(`/api/v1/projects/${projectId}/uploads`, { method: "POST", body: fd });
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
            <>
              <p className="text-lg font-semibold text-gray-800">Start your thesis</p>
              <p className="mt-1 text-sm max-w-md">
                Type your research topic below and I&apos;ll guide you step by
                step — or hit Auto-draft to generate a full draft.
              </p>
            </>
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
      <ChatInput onSubmit={send} onFileDrop={onFileDrop} disabled={inflight} />

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
