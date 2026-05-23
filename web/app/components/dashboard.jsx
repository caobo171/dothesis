"use client";

import Link from "next/link";
import { Icon } from "./icons";
import { Topbar } from "./shared";
import { useAuth } from "../lib/auth-context";

export const Dashboard = ({ papers = [], loading = false, error = null }) => {
  const { user } = useAuth();
  const name = user?.email?.split("@")[0] || "researcher";

  return (
    <div className="main">
      <Topbar crumbs={["Workspace", "Dashboard"]} />
      <div
        className="canvas"
        style={{ maxWidth: 1080, margin: "0 auto", width: "100%", gap: 28, paddingTop: 56 }}
      >
        {/* Hero */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 30,
                fontWeight: 800,
                letterSpacing: "-0.02em",
                margin: 0,
                lineHeight: 1.1,
              }}
            >
              Welcome back, {name}.
            </h1>
            <p style={{ fontSize: 14, color: "var(--ink-500)", marginTop: 8 }}>
              {loading
                ? "Loading your drafts…"
                : papers.length === 0
                ? "No drafts yet — start your first one."
                : `${papers.length} ${papers.length === 1 ? "paper" : "papers"} in your workspace.`}
            </p>
          </div>
          <Link
            href="/wizard"
            className="btn btn-primary btn-lg"
            style={{ padding: "14px 20px" }}
          >
            <Icon name="plus" size={16} stroke={2.5} /> New Paper
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

        {!loading && papers.length === 0 && !error && (
          <div
            className="card"
            style={{ padding: 48, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}
          >
            <Icon name="feather" size={36} stroke={1.5} style={{ color: "var(--blue-600)" }} />
            <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>Start your first thesis</h2>
            <p style={{ color: "var(--ink-500)", fontSize: 13, margin: 0, maxWidth: 360 }}>
              Pick a topic, choose your settings, and the agents will draft a fully cited paper in minutes.
            </p>
            <Link href="/wizard" className="btn btn-primary" style={{ marginTop: 4 }}>
              <Icon name="plus" size={14} /> New Paper
            </Link>
          </div>
        )}

        {/* Papers list */}
        {papers.length > 0 && (
          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 14,
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-700)" }}>
                {papers.length} {papers.length === 1 ? "paper" : "papers"}
              </div>
            </div>

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
          </div>
        )}
      </div>
    </div>
  );
};

const PaperRow = ({ p, divider }) => {
  const tab = p.status === "done" ? "editor" : "run";
  return (
    <Link
      href={`/paper/${p.id}?tab=${tab}`}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 130px 110px 100px",
        gap: 18,
        alignItems: "center",
        padding: "18px 22px",
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
            fontFamily: "var(--font-serif)",
            fontSize: 16.5,
            fontWeight: 600,
            color: "var(--ink-900)",
            letterSpacing: "-0.01em",
            lineHeight: 1.3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {p.title}
        </div>
        <div
          style={{
            fontSize: 12,
            color: "var(--ink-500)",
            marginTop: 4,
            display: "flex",
            gap: 10,
          }}
        >
          <span>{p.level || "—"}</span>
        </div>
      </div>

      {/* Progress */}
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
              width: `${(p.progress || 0) * 100}%`,
              height: "100%",
              background:
                p.status === "done"
                  ? "var(--ok-fg)"
                  : p.status === "failed"
                  ? "var(--stop-fg)"
                  : "var(--blue-600)",
            }}
          />
        </div>
      </div>

      <StatusPill status={p.status} />

      <div
        style={{
          textAlign: "right",
          fontSize: 12,
          color: "var(--ink-400)",
          fontWeight: 600,
        }}
      >
        {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : ""}
      </div>
    </Link>
  );
};

const StatusPill = ({ status }) => {
  const m =
    {
      running: { fg: "var(--blue-600)", label: "Generating" },
      done: { fg: "var(--ok-fg)", label: "Complete" },
      failed: { fg: "var(--stop-fg)", label: "Failed" },
      draft: { fg: "var(--ink-400)", label: "Draft" },
    }[status] || { fg: "var(--ink-400)", label: status || "—" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        fontWeight: 700,
        color: m.fg,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: m.fg,
          animation: status === "running" ? "pulse 1.6s ease-in-out infinite" : "none",
        }}
      />
      {m.label}
    </span>
  );
};
