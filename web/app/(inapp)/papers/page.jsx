"use client";

import Link from "next/link";
import useSWR from "swr";
import { swrFetcher } from "../../lib/api";

export default function PapersPage() {
  const { data: papers = [], error, isLoading } = useSWR("/papers", swrFetcher);

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto", width: "100%" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 18,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 800,
              letterSpacing: "-0.015em",
              margin: 0,
              color: "var(--ink-900)",
            }}
          >
            Drafts
          </h1>
          <p style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 4 }}>
            {isLoading
              ? "Loading…"
              : `${papers.length} ${papers.length === 1 ? "paper" : "papers"} in your workspace.`}
          </p>
        </div>
        <Link
          href="/wizard"
          className="btn btn-primary"
          style={{ padding: "10px 16px", fontSize: 14 }}
        >
          + New Paper
        </Link>
      </div>

      {error && (
        <div
          style={{
            padding: 14,
            background: "var(--stop-bg)",
            color: "var(--stop-fg)",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          {error.message || "Could not load papers"}
        </div>
      )}

      {!isLoading && papers.length === 0 && !error && (
        <div
          style={{
            padding: 40,
            textAlign: "center",
            background: "var(--paper)",
            border: "1px dashed var(--ink-200)",
            borderRadius: 14,
            color: "var(--ink-500)",
            fontSize: 14,
          }}
        >
          No drafts yet. <Link href="/wizard" style={{ color: "var(--blue-600)", fontWeight: 600 }}>Start one →</Link>
        </div>
      )}

      {papers.length > 0 && (
        <div
          style={{
            background: "var(--paper)",
            border: "1px solid var(--ink-100)",
            borderRadius: 14,
            overflow: "hidden",
          }}
        >
          {papers.map((p, i) => (
            <PaperRow key={p.id} p={p} divider={i < papers.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function PaperRow({ p, divider }) {
  const tab = p.status === "done" ? "editor" : "run";
  const statusColor =
    {
      running: "var(--blue-600)",
      done: "var(--ok-fg)",
      failed: "var(--stop-fg)",
      canceled: "var(--ink-400)",
    }[p.status] || "var(--ink-400)";

  return (
    <Link
      href={`/paper/${p.id}?tab=${tab}`}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 130px 110px 100px",
        gap: 18,
        alignItems: "center",
        padding: "16px 22px",
        borderBottom: divider ? "1px solid var(--ink-100)" : "none",
        textDecoration: "none",
        color: "inherit",
        transition: "background 0.12s",
      }}
      className="paper-row"
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 14.5,
            fontWeight: 700,
            color: "var(--ink-900)",
            letterSpacing: "-0.005em",
            lineHeight: 1.3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {p.title}
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4 }}>
          {p.level || "—"}
        </div>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 11, color: "var(--ink-400)", fontWeight: 700 }}>
            {Math.round((p.progress || 0) * 100)}%
          </span>
        </div>
        <div
          style={{
            background: "var(--ink-100)",
            borderRadius: 999,
            height: 4,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${Math.round((p.progress || 0) * 100)}%`,
              height: "100%",
              background: statusColor,
              transition: "width 0.4s ease",
            }}
          />
        </div>
      </div>

      <div style={{ fontSize: 12, fontWeight: 600, color: statusColor, textTransform: "capitalize" }}>
        {p.status}
      </div>

      <div style={{ fontSize: 12, color: "var(--ink-400)", textAlign: "right" }}>
        {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : "—"}
      </div>
    </Link>
  );
}
