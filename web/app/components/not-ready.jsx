"use client";

import Link from "next/link";
import { Icon } from "./icons";

/**
 * Shared banner used by Draft / Citations / Export tabs while the job is still running
 * (the underlying API returns 409 "not_ready" — we turn that into a friendly state).
 * `kind` is "draft" | "citations" | "exports".
 */
export const NotReady = ({ paperId, kind = "draft", error }) => {
  const titles = {
    draft:     "Draft not ready yet",
    citations: "Citations not ready yet",
    exports:   "Exports not ready yet",
  };
  const subtitles = {
    draft:     "Your thesis is still being generated. The full text will appear here when all six phases finish.",
    citations: "The verified bibliography appears here once the engine finishes citation verification.",
    exports:   "PDF, DOCX, LaTeX and Markdown will appear here as soon as the engine finishes the Export phase.",
  };

  // If the API returned anything other than 409, show the raw message — that's a real error.
  const realError = error && error.status !== 409;

  return (
    <div className="canvas" style={{ padding: 32 }}>
      <div className="card" style={{ padding: 28, display: "flex", gap: 18, alignItems: "flex-start" }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: "var(--blue-50)", color: "var(--blue-600)",
          display: "grid", placeItems: "center", flexShrink: 0,
        }}>
          <Icon name={realError ? "warn" : "pipeline"} size={22} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: "var(--ink-900)" }}>
            {realError ? "Something went wrong" : titles[kind]}
          </div>
          <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 6, lineHeight: 1.5 }}>
            {realError ? error.message : subtitles[kind]}
          </div>
          {!realError && (
            <Link href={`/paper/${paperId}?tab=run`} className="btn btn-primary btn-sm" style={{ marginTop: 14 }}>
              <Icon name="pipeline" size={13} /> Watch live progress
            </Link>
          )}
        </div>
      </div>
    </div>
  );
};
