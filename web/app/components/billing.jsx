"use client";

import { Icon } from "./icons";
import { Topbar, Card, KPI } from "./shared";

const USAGE = [
  { date: "Mar 18", draft: "Algorithmic Decision-Making…", model: "Sonnet 4.5", cost: 142 },
  { date: "Mar 14", draft: "Mental Health Outcomes of Hybrid Work…", model: "Sonnet 4.5", cost: 118 },
  { date: "Mar 12", draft: "Coastal Adaptation (PhD)", model: "Opus", cost: 296 },
  { date: "Mar 09", draft: "Decentralized Identity Frameworks…", model: "Gemini Flash", cost: 34 },
  { date: "Mar 04", draft: "LLMs in Higher Education Assessment", model: "Sonnet 4.5", cost: 121 },
];

const PLANS = [
  { id: "free", label: "Reader", price: "300", per: "credits / day", desc: "On the house — refreshes daily", features: [
    "3 short drafts / day", "Research papers (5k words)", "PDF + DOCX export", "Community support",
  ], cta: "Downgrade" },
  { id: "pro", label: "Scholar — Pro", price: "5,000", per: "credits / mo", desc: "Master's-grade everything", features: [
    "≈ 35 master's drafts / mo", "All academic levels", "All citation styles", "LaTeX export", "Priority queue", "Email support",
  ], cta: "You're on this", current: true },
  { id: "max", label: "Scholar — Max", price: "20,000", per: "credits / mo", desc: "PhD dissertations + journal", features: [
    "≈ 65 PhD chapters / mo", "Claude Opus + GPT-5", "Journal template library", "Advisor share-link", "Live writing coach (Mon–Fri)",
  ], cta: "Upgrade" },
];

export const Billing = () => (
  <div className="main">
    <Topbar crumbs={["Account", "Credits & Billing"]} />
    <div className="canvas">
      <div>
        <div className="eyebrow">Account</div>
        <h1 className="page-title" style={{ marginTop: 6 }}>
          Credits, plans, and <span className="accent">runs.</span>
        </h1>
        <p className="page-subtitle">
          DoThesis is metered per draft — you pay the API cost plus a small operating margin. No surprises.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 16 }}>
        <div style={{
          background: "linear-gradient(155deg, #161827 0%, #1c2eff 100%)",
          color: "white", borderRadius: 18, padding: 24,
          position: "relative", overflow: "hidden",
        }}>
          <div style={{ position: "absolute", right: -30, top: -30, width: 160, height: 160,
            background: "radial-gradient(closest-side, rgba(255,255,255,0.18), transparent 70%)" }} />
          <div className="eyebrow" style={{ color: "rgba(255,255,255,0.7)" }}>Credit balance</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 8 }}>
            <div style={{ fontSize: 48, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1 }}>5,756</div>
            <div style={{ fontSize: 18, fontWeight: 600, opacity: 0.7 }}>credits</div>
          </div>
          <div style={{ fontSize: 13, opacity: 0.7, marginTop: 4 }}>≈ 41 master&apos;s drafts at current rate</div>
          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            <button className="btn" style={{ background: "white", color: "var(--ink-900)" }}>
              <Icon name="plus" size={14}/> Top up credits
            </button>
            <button className="btn btn-ghost" style={{ color: "white", border: "1px solid rgba(255,255,255,0.2)" }}>
              <Icon name="export" size={14}/> Auto-recharge
            </button>
          </div>
        </div>
        <KPI label="Credits used · month" value="821" sub="across 14 drafts" />
        <KPI label="Avg / draft" value="58" sub="credits · Sonnet 4.5" accent="var(--blue-600)" />
        <KPI label="Days remaining" value="68" sub="at current burn rate" accent="var(--ok-fg)" />
      </div>

      <Card title="Plans" subtitle="Switch any time. Pro-rated automatically." padded={false}>
        <div style={{ padding: 24, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
          {PLANS.map((p) => <PlanCard key={p.id} {...p} />)}
        </div>
      </Card>

      <Card padded={false} title="Recent runs"
        subtitle="Each row is a full agent pipeline run."
        action={<button className="btn btn-ghost btn-sm"><Icon name="export" size={12}/> Download invoice (PDF)</button>}>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th><th>Draft</th><th>Model</th><th>Cost</th><th></th>
            </tr>
          </thead>
          <tbody>
            {USAGE.map((u, i) => (
              <tr key={i}>
                <td style={{ color: "var(--ink-500)", fontWeight: 600 }}>{u.date}</td>
                <td className="row-title">{u.draft}</td>
                <td>
                  <span style={{
                    fontSize: 11, fontWeight: 800, letterSpacing: "0.04em",
                    color: "var(--blue-600)", background: "var(--blue-50)",
                    padding: "3px 8px", borderRadius: 999,
                  }}>{u.model}</span>
                </td>
                <td style={{ fontWeight: 800, fontFamily: "var(--font-mono)" }}>{u.cost} <span style={{ fontWeight: 500, color: "var(--ink-400)", fontSize: 12 }}>cr</span></td>
                <td><button className="btn btn-ghost btn-sm">View receipt</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  </div>
);

const PlanCard = ({ label, price, per, desc, features, cta, current }) => (
  <div style={{
    border: current ? "2px solid var(--blue-600)" : "1.5px solid var(--ink-200)",
    background: current ? "var(--blue-50)" : "var(--paper)",
    borderRadius: 16,
    padding: 22,
    position: "relative",
  }}>
    {current && (
      <span style={{
        position: "absolute", top: -10, right: 16,
        background: "var(--blue-600)", color: "white",
        fontSize: 10.5, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
        letterSpacing: 0.4,
      }}>YOUR PLAN</span>
    )}
    <div style={{ fontWeight: 800, fontSize: 17 }}>{label}</div>
    <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 3 }}>{desc}</div>
    <div style={{ marginTop: 18, display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
      <span style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.02em" }}>{price}</span>
      <span style={{ color: "var(--ink-500)", fontSize: 13, fontWeight: 600 }}>{per}</span>
    </div>
    <ul style={{ listStyle: "none", padding: 0, margin: "18px 0 0", display: "flex", flexDirection: "column", gap: 10 }}>
      {features.map((f, i) => (
        <li key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, color: "var(--ink-700)" }}>
          <Icon name="check" size={14} stroke={3} style={{ color: "var(--ok-fg)", marginTop: 2, flexShrink: 0 }} />
          {f}
        </li>
      ))}
    </ul>
    <button
      className={current ? "btn btn-ghost btn-block" : "btn btn-primary btn-block"}
      style={{ marginTop: 22 }}
      disabled={current}
    >
      {cta}
    </button>
  </div>
);
