"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "./icons";
import { apiFetch, ApiError } from "../lib/api";

export const PaperShell = ({ paper, jobId, latestJob, tab, setTab, onJobChanged, children }) => {
  const tabs = [
    { id: "run", label: "Generation" },
    { id: "editor", label: "Draft" },
    { id: "citations", label: "Citations" },
    { id: "export", label: "Export" },
  ];

  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState(null);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState(null);

  const stop = async () => {
    if (!jobId) return;
    if (!confirm("Stop this run? You can resume later if a checkpoint has been saved.")) return;
    setStopping(true);
    setStopError(null);
    try {
      await apiFetch(`/jobs/${jobId}/cancel`, { method: "POST" });
      onJobChanged?.();
    } catch (e) {
      setStopError(e instanceof ApiError ? e.message : "Could not stop job");
    } finally {
      setStopping(false);
    }
  };

  const resume = async () => {
    setResuming(true);
    setResumeError(null);
    try {
      const resp = await apiFetch(`/papers/${paper.id}/resume`, { method: "POST" });
      onJobChanged?.();
      // Navigating to the run tab so the user sees progress streaming.
      setTab("run");
      if (resp?.resumed_from_phase) {
        // Small toast-style hint via console; visible state-change is the running banner itself.
        console.info(`Resumed from phase: ${resp.resumed_from_phase}`);
      }
    } catch (e) {
      const code = e?.body?.error?.code;
      if (code === "no_checkpoint") {
        setResumeError("No checkpoint was saved before this job stopped — nothing to resume from.");
      } else if (code === "already_running") {
        setResumeError("You already have a job running. Wait for it to finish first.");
      } else {
        setResumeError(e instanceof ApiError ? e.message : "Could not resume");
      }
    } finally {
      setResuming(false);
    }
  };

  const canResume =
    (paper.status === "failed" || paper.status === "canceled") &&
    latestJob?.has_checkpoint === true;

  const statusLabel =
    {
      running: "Generating",
      done: "Complete",
      failed: "Failed",
      draft: "Draft",
    }[paper.status] || paper.status || "";

  const statusColor =
    {
      running: "var(--blue-600)",
      done: "var(--ok-fg)",
      failed: "var(--stop-fg)",
    }[paper.status] || "var(--ink-400)";

  return (
    <div className="main">
      <div
        style={{
          background: "var(--paper)",
          borderBottom: "1px solid var(--ink-100)",
          padding: "16px 40px 0",
        }}
      >
        {/* Title row */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 36 }}>
          <Link
            href="/"
            style={{
              padding: "6px 8px",
              color: "var(--ink-500)",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 13,
              fontWeight: 600,
              borderRadius: 8,
              textDecoration: "none",
            }}
          >
            <Icon name="arrow-left" size={14} />
          </Link>
          <div
            style={{
              flex: 1,
              minWidth: 0,
              fontFamily: "var(--font-serif)",
              fontSize: 17,
              fontWeight: 600,
              letterSpacing: "-0.005em",
              color: "var(--ink-900)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {paper.title}
          </div>
          {paper.status === "running" && jobId && (
            <button
              type="button"
              onClick={stop}
              disabled={stopping}
              className="btn btn-ghost btn-sm"
              style={{ color: "var(--stop-fg)", fontWeight: 700 }}
            >
              <Icon name="stop" size={12} /> {stopping ? "Stopping…" : "Stop"}
            </button>
          )}
          {canResume && (
            <button
              type="button"
              onClick={resume}
              disabled={resuming}
              className="btn btn-secondary btn-sm"
            >
              <Icon name="play" size={12} /> {resuming ? "Resuming…" : `Resume${latestJob?.completed_phase ? ` from ${latestJob.completed_phase}` : ""}`}
            </button>
          )}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12.5,
              fontWeight: 700,
              color: statusColor,
              flexShrink: 0,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: 999,
                background: statusColor,
                animation:
                  paper.status === "running" ? "pulse 1.6s ease-in-out infinite" : "none",
              }}
            />
            {statusLabel}
          </span>
        </div>

        {(stopError || resumeError) && (
          <div
            style={{
              marginTop: 8,
              fontSize: 12,
              color: "var(--stop-fg)",
              fontWeight: 600,
            }}
          >
            {stopError || resumeError}
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginTop: 14 }}>
          {tabs.map((tb) => (
            <button
              key={tb.id}
              type="button"
              onClick={() => setTab(tb.id)}
              style={{
                padding: "10px 14px 12px",
                border: "none",
                background: "transparent",
                fontWeight: 700,
                fontSize: 13.5,
                color: tab === tb.id ? "var(--ink-900)" : "var(--ink-500)",
                cursor: "pointer",
                position: "relative",
              }}
            >
              {tb.label}
              {tab === tb.id && (
                <span
                  style={{
                    position: "absolute",
                    left: 12,
                    right: 12,
                    bottom: -1,
                    height: 2,
                    background: "var(--blue-600)",
                  }}
                />
              )}
            </button>
          ))}
        </div>
      </div>

      {children}
    </div>
  );
};
