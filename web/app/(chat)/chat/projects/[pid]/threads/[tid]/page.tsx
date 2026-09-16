"use client";

import { useContext, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ChatPane } from "@/app/components/chat/ChatPane";
import { ThesisEditor } from "@/app/components/editor/ThesisEditor";
import { WorkspaceModeContext } from "@/app/components/chat/ChatShellLayout";


export default function ThreadPage() {
  const params = useParams<{ pid: string; tid: string }>();
  const searchParams = useSearchParams();
  const mode = searchParams.get("mode") === "editor" ? "editor" : "chat";
  const workspace = useContext(WorkspaceModeContext);

  function setMode(nextMode: "chat" | "editor") {
    if (nextMode === mode) return;
    // Decision: Next's native history integration updates search params without
    // remounting either surface; reload and Back/Forward use the same URL state.
    const url = new URL(window.location.href);
    url.searchParams.set("mode", nextMode);
    window.history.pushState(null, "", url);
  }

  useEffect(() => {
    workspace.setEditorMode(mode === "editor");
    return () => workspace.setEditorMode(false);
  }, [mode, workspace.setEditorMode]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {/* Keep both surfaces mounted. CSS visibility switches the primary mode,
          preserving the editor selection/draft and any in-flight agent turn. */}
      <section aria-hidden={mode !== "chat"} className={mode === "chat" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <ChatPane projectId={params.pid} threadId={params.tid} onOpenEditor={() => setMode("editor")} />
      </section>
      <section aria-hidden={mode !== "editor"} className={mode === "editor" ? "min-h-0 flex-1" : "hidden"}>
        <ThesisEditor projectId={params.pid} onBackToChat={() => setMode("chat")} />
      </section>
    </div>
  );
}
