"use client";

import Link from "next/link";
import { Icon } from "./icons";
import { Topbar, Badge, Card, ProgressBar, KPI } from "./shared";

export const Dashboard = ({ papers = [], loading = false, error = null, refresh }) => (
  <div className="main">
    <Topbar crumbs={["Workspace", "Dashboard"]} />
    <div className="canvas">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 24 }}>
        <div>
          <div className="eyebrow">Welcome back</div>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            Hi — let&apos;s <span className="accent">finish your thesis.</span>
          </h1>
          <p className="page-subtitle">
            Resume a draft, or start a new one and let the agents do the heavy lift.
          </p>

          <Link
            href="/wizard"
            className="btn btn-primary btn-lg"
            style={{ marginTop: 22, width: "100%", padding: "20px", fontSize: 16, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, textDecoration: "none" }}
          >
            <Icon name="plus" size={20} stroke={2.5} />
            Start a new thesis
            <span style={{
              marginLeft: 8, padding: "3px 8px", background: "rgba(255,255,255,0.18)",
              borderRadius: 8, fontSize: 11, fontWeight: 700, letterSpacing: 0.4,
            }}>10–20 MIN</span>
          </Link>
        </div>

        <div style={{
          background: "linear-gradient(155deg, #161827 0%, #1c2eff 100%)",
          color: "white",
          borderRadius: 18,
          padding: 22,
          position: "relative",
          overflow: "hidden",
        }}>
          <div style={{ position: "absolute", right: -40, top: -40, width: 180, height: 180,
            background: "radial-gradient(closest-side, rgba(255,255,255,0.18), transparent 70%)" }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div className="eyebrow" style={{ color: "rgba(255,255,255,0.7)" }}>Credit balance</div>
            <Icon name="spark" size={20} style={{ color: "rgba(255,255,255,0.6)" }} />
          </div>
          <div style={{ fontSize: 36, fontWeight: 800, marginTop: 8, letterSpacing: "-0.02em", display: "flex", alignItems: "baseline", gap: 8 }}>
            5,756 <span style={{ fontSize: 16, opacity: 0.7, fontWeight: 600, letterSpacing: 0 }}>credits</span>
          </div>
          <div style={{ fontSize: 13, opacity: 0.7, marginTop: 4 }}>
            ≈ 41 master&apos;s drafts · 19 PhD chapters
          </div>
          <div style={{
            marginTop: 18, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.12)",
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 12,
          }}>
            <div>
              <div style={{ opacity: 0.6, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>Role</div>
              <div style={{ marginTop: 3, fontSize: 14, fontWeight: 700 }}>Scholar — Pro</div>
            </div>
            <div>
              <div style={{ opacity: 0.6, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>User ID</div>
              <div style={{ marginTop: 3, fontSize: 14, fontWeight: 700 }}>1005</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
        <KPI label="Drafts this month" value="14" sub="+4 vs last month" accent="var(--blue-600)" />
        <KPI label="Words generated" value="186,420" sub="across 14 drafts" />
        <KPI label="Citations verified" value="1,284" sub="98.7% real sources" accent="var(--ok-fg)" />
        <KPI label="Avg. draft time" value="14m 22s" sub="Master's · Claude Sonnet" />
      </div>

      {loading && <div style={{ padding: 16, color: "var(--ink-500)" }}>Loading…</div>}
      {error && <div style={{ padding: 16, color: "var(--danger-fg)" }}>Error: {error.message}</div>}

      {papers.length === 0 && !loading ? (
        <div className="empty" style={{ padding: 48, textAlign: "center" }}>
          <h2>No drafts yet</h2>
          <p style={{ color: "var(--ink-500)", margin: "8px 0 16px" }}>Start your first thesis from the wizard.</p>
          <Link href="/wizard" className="btn btn-primary">New thesis</Link>
        </div>
      ) : (
        <Card
          title="Your drafts"
          subtitle="Resume an active draft or open a finished one."
          padded={false}
          action={
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm">
                <Icon name="filter" size={14} /> Filter
              </button>
              <button className="btn btn-secondary btn-sm">
                <Icon name="search" size={14} /> Search
              </button>
            </div>
          }
        >
          <table className="table">
            <thead>
              <tr>
                <th></th>
                <th>Title</th>
                <th>Level</th>
                <th>Progress</th>
                <th>Status</th>
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {papers.map((p, i) => (
                <tr key={p.id} className="draft-row" style={{ cursor: "pointer" }}>
                  <td className="row-num">{String(i + 1).padStart(2, "0")}</td>
                  <td>
                    <Link
                      href={`/paper/${p.id}?tab=run`}
                      style={{ textDecoration: "none", color: "inherit" }}
                    >
                      <div className="row-title">{p.title}</div>
                    </Link>
                  </td>
                  <td>
                    <span style={{
                      padding: "3px 10px",
                      background: "var(--ink-50)",
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--ink-700)",
                      whiteSpace: "nowrap",
                    }}>{p.level}</span>
                  </td>
                  <td style={{ minWidth: 120 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <ProgressBar
                        value={p.progress ?? 0}
                        color={
                          p.status === "stop" ? "var(--stop-fg)" :
                          p.status === "pause" ? "var(--pause-fg)" :
                          p.status === "ok" ? "var(--ok-fg)" : "var(--blue-600)"
                        }
                      />
                      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-700)", minWidth: 32 }}>
                        {Math.round((p.progress ?? 0) * 100)}%
                      </span>
                    </div>
                  </td>
                  <td><Badge status={p.status} /></td>
                  <td style={{ color: "var(--ink-400)", fontSize: 13 }}>
                    {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : "—"}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: "flex", gap: 6 }}>
                      <Link
                        href={`/paper/${p.id}?tab=run`}
                        className="iconbtn"
                        style={{ width: 32, height: 32, background: "var(--blue-50)", color: "var(--blue-600)", border: "none", display: "grid", placeItems: "center" }}
                      >
                        <Icon name="eye" size={14} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <Card padded={false}>
          <div style={{ padding: "20px 24px", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <Badge status="running" />
              <div className="section-title" style={{ marginTop: 10 }}>
                Algorithmic Decision-Making and Democratic Accountability
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 4 }}>
                Crafter · Discussion is currently writing §5.2 — Implications for transatlantic harmonization
              </div>
            </div>
          </div>
          <hr className="hr" />
          <div style={{ padding: "18px 24px", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 18 }}>
            <Mini label="Progress" value="62%" />
            <Mini label="Words" value="14,820" sub="of 27k target" />
            <Mini label="Citations verified" value="32" sub="of 32 found" />
            <Mini label="ETA" value="6m 14s" />
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 12,
              background: "var(--blue-50)", color: "var(--blue-600)",
              display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <Icon name="sparkle" />
            </div>
            <div>
              <div style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-400)", fontWeight: 700 }}>
                Pro tip
              </div>
              <div style={{ fontWeight: 700, marginTop: 4 }}>Give Scout a research question, not a topic.</div>
              <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 8, lineHeight: 1.5 }}>
                &quot;How do EU and US AI regulations diverge on enforcement?&quot; produces tighter literature than &quot;AI regulation.&quot;
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  </div>
);

const Mini = ({ label, value, sub }) => (
  <div>
    <div style={{ fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-400)", fontWeight: 700 }}>
      {label}
    </div>
    <div style={{ fontSize: 22, fontWeight: 800, marginTop: 4, letterSpacing: "-0.01em" }}>{value}</div>
    {sub && <div style={{ fontSize: 12, color: "var(--ink-500)" }}>{sub}</div>}
  </div>
);
