"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "./icons";
import { Topbar, ProgressBar } from "./shared";
import { apiFetch, ApiError } from "../lib/api";

export const PaperShell = ({ paper, jobId, tab, setTab, onJobChanged, children }) => {
  const tabs = [
    { id: "run",       label: "Live progress", icon: "pipeline" },
    { id: "editor",    label: "Draft",         icon: "edit" },
    { id: "citations", label: "Citations",     icon: "quote" },
    { id: "export",    label: "Export",        icon: "export" },
  ];

  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState(null);

  const stop = async () => {
    if (!jobId) return;
    if (!confirm("Stop this run? Partial output will not be saved.")) return;
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

  return (
    <div className="main">
      <Topbar
        crumbs={["Workspace", "Dashboard", paper.title]}
        rightExtra={
          <div style={{ display: "flex", gap: 8 }}>
            {paper.status === "running" && (
              <span className="badge run"><span className="pulse" />Pipeline running</span>
            )}
            {paper.status === "ok" && (
              <span className="badge ok"><Icon name="check" size={12} stroke={3}/> Draft complete</span>
            )}
            {paper.status === "pause" && (
              <span className="badge pause">Paused</span>
            )}
          </div>
        }
      />

      <div style={{
        background: "var(--paper)",
        borderBottom: "1px solid var(--ink-100)",
        padding: "20px 40px 0",
      }}>
        <Link
          href="/"
          className="btn btn-ghost btn-sm"
          style={{ padding: "6px 10px", marginLeft: -10 }}
        >
          <Icon name="arrow-left" size={14} /> Back to dashboard
        </Link>

        <div style={{ display: "flex", gap: 24, alignItems: "flex-end", marginTop: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="eyebrow">{paper.level} · {paper.discipline}</span>
              <span style={{
                fontSize: 11, fontWeight: 700, color: "var(--blue-600)",
                padding: "3px 8px", background: "var(--blue-50)", borderRadius: 999,
                letterSpacing: 0.4,
              }}>CLAUDE SONNET 4.5</span>
              <span style={{ fontSize: 11, color: "var(--ink-400)", fontWeight: 600 }}>
                Run #4821 · Started 09:42
              </span>
            </div>
            <div style={{
              fontFamily: "var(--font-serif)", fontSize: 26, fontWeight: 600,
              letterSpacing: "-0.01em", marginTop: 8, lineHeight: 1.2,
            }}>
              {paper.title}
            </div>
            {paper.subtitle && (
              <div style={{
                fontFamily: "var(--font-serif)", fontSize: 16, fontStyle: "italic",
                color: "var(--ink-500)", marginTop: 4,
              }}>
                {paper.subtitle}
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            {paper.status === "running" && (
              <>
                <button className="btn btn-secondary" onClick={stop} disabled={stopping || !jobId}>
                  <Icon name="stop" size={14}/> {stopping ? "Stopping…" : "Stop"}
                </button>
                {stopError && (
                  <span style={{ fontSize: 11, color: "var(--danger-fg)", alignSelf: "center" }}>
                    {stopError}
                  </span>
                )}
              </>
            )}
            {paper.status === "ok" && (
              <>
                <button className="btn btn-ghost"><Icon name="copy" size={14}/> Duplicate</button>
                <button className="btn btn-primary" onClick={() => setTab("export")}>
                  <Icon name="export" size={14}/> Export
                </button>
              </>
            )}
            {paper.status === "pause" && (
              <button className="btn btn-primary"><Icon name="play" size={14}/> Resume</button>
            )}
          </div>
        </div>

        <div style={{
          marginTop: 22, display: "grid",
          gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr", gap: 28, alignItems: "center",
        }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 11, color: "var(--ink-500)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Overall pipeline
              </span>
              <span style={{ fontSize: 12, color: "var(--blue-600)", fontWeight: 800 }}>
                {Math.round(paper.progress * 100)}%
              </span>
            </div>
            <ProgressBar value={paper.progress} height={8} />
          </div>
          <Mini2 label="Words" value={(paper.words ?? 0).toLocaleString()} sub="" />
          <Mini2 label="Citations" value={paper.citations != null ? `${paper.citations}` : "—"} sub="" accent="var(--ok-fg)" />
          <Mini2 label="Status" value={paper.status || "—"} />
          <Mini2 label="Level" value={paper.level || "—"} accent="var(--blue-600)" />
        </div>

        <div style={{ display: "flex", gap: 4, marginTop: 22 }}>
          {tabs.map((tb) => (
            <button
              key={tb.id}
              onClick={() => setTab(tb.id)}
              style={{
                padding: "12px 18px 14px",
                border: "none",
                background: "transparent",
                fontWeight: 700,
                fontSize: 13.5,
                color: tab === tb.id ? "var(--blue-600)" : "var(--ink-500)",
                cursor: "pointer",
                position: "relative",
                display: "inline-flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <Icon name={tb.icon} size={15} stroke={tab === tb.id ? 2.4 : 1.8} />
              {tb.label}
              {tab === tb.id && (
                <span style={{
                  position: "absolute",
                  left: 12, right: 12, bottom: -1, height: 3,
                  background: "var(--blue-600)",
                  borderRadius: "3px 3px 0 0",
                }} />
              )}
            </button>
          ))}
        </div>
      </div>

      {children}
    </div>
  );
};

const Mini2 = ({ label, value, sub, accent }) => (
  <div>
    <div style={{ fontSize: 10.5, color: "var(--ink-400)", letterSpacing: "0.08em",
                  textTransform: "uppercase", fontWeight: 700 }}>{label}</div>
    <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2,
                  color: accent || "var(--ink-900)", letterSpacing: "-0.02em", lineHeight: 1.05 }}>
      {value}
    </div>
    {sub && <div style={{ fontSize: 11, color: "var(--ink-400)" }}>{sub}</div>}
  </div>
);
