// Dashboard — simple, list-first.

const Dashboard = ({ go }) => {
  const { Badge } = window.SHARED;
  const { RECENT_DRAFTS } = window.DOTHESIS;

  return (
    <div className="main">
      <div className="canvas" style={{ maxWidth: 1080, margin: "0 auto", width: "100%", gap: 28, paddingTop: 56 }}>
        {/* Hero */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{
              fontSize: 30, fontWeight: 800, letterSpacing: "-0.02em", margin: 0, lineHeight: 1.1,
            }}>
              Welcome back, jeendeet.
            </h1>
            <p style={{ fontSize: 14, color: "var(--ink-500)", marginTop: 8 }}>
              You have <b style={{ color: "var(--ink-900)" }}>9 credits</b> remaining ·
              <button onClick={() => go("billing")} style={{ background: "none", border: "none", color: "var(--blue-600)", fontWeight: 700, cursor: "pointer", padding: "0 4px" }}>
                Top up
              </button>
            </p>
          </div>
          <button
            className="btn btn-primary btn-lg"
            onClick={() => go("wizard")}
            style={{ padding: "14px 20px" }}
          >
            <Icon name="plus" size={16} stroke={2.5} /> New Paper
          </button>
        </div>

        {/* Papers list */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-700)" }}>
              {RECENT_DRAFTS.length} papers
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost btn-sm" style={{ padding: "6px 10px" }}>
                <Icon name="search" size={14} />
              </button>
              <button className="btn btn-ghost btn-sm" style={{ padding: "6px 10px" }}>
                <Icon name="filter" size={14} />
              </button>
            </div>
          </div>

          <div style={{
            background: "var(--paper)",
            border: "1px solid var(--ink-100)",
            borderRadius: 14,
            overflow: "hidden",
          }}>
            {RECENT_DRAFTS.map((d, i) => (
              <PaperRow key={d.id} d={d} go={go}
                divider={i < RECENT_DRAFTS.length - 1} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const PaperRow = ({ d, go, divider }) => {
  const tab = d.status === "ok" ? "editor" : "run";
  return (
    <button
      onClick={() => go("paper", { paperId: d.id, tab })}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 130px 110px 100px",
        gap: 18,
        alignItems: "center",
        padding: "18px 22px",
        borderBottom: divider ? "1px solid var(--ink-100)" : "none",
        background: "transparent",
        border: "none",
        borderBottomLeftRadius: 0,
        textAlign: "left",
        cursor: "pointer",
        width: "100%",
        transition: "background 0.12s",
      }}
      onMouseEnter={(e) => e.currentTarget.style.background = "var(--ink-50)"}
      onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontFamily: "var(--font-serif)",
          fontSize: 16.5,
          fontWeight: 600,
          color: "var(--ink-900)",
          letterSpacing: "-0.01em",
          lineHeight: 1.3,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}>
          {d.title}
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4, display: "flex", gap: 10 }}>
          <span>{d.discipline}</span>
          <span style={{ color: "var(--ink-300)" }}>·</span>
          <span>{d.level}</span>
        </div>
      </div>

      {/* Progress */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 11, color: "var(--ink-400)", fontWeight: 700 }}>
            {d.words.toLocaleString()}w
          </span>
          <span style={{ fontSize: 11, color: "var(--ink-700)", fontWeight: 700 }}>
            {Math.round(d.progress * 100)}%
          </span>
        </div>
        <div style={{ background: "var(--ink-100)", borderRadius: 999, height: 4, overflow: "hidden" }}>
          <div style={{
            width: `${d.progress * 100}%`,
            height: "100%",
            background: d.status === "ok"   ? "var(--ok-fg)" :
                        d.status === "pause" ? "var(--pause-fg)" :
                        d.status === "stop" ? "var(--stop-fg)" : "var(--blue-600)",
          }} />
        </div>
      </div>

      <StatusPill status={d.status} />

      <div style={{ textAlign: "right", fontSize: 12, color: "var(--ink-400)", fontWeight: 600 }}>
        {d.updated}
      </div>
    </button>
  );
};

const StatusPill = ({ status }) => {
  const m = {
    running: { fg: "var(--blue-600)", label: "Generating" },
    ok:      { fg: "var(--ok-fg)",    label: "Complete" },
    pause:   { fg: "var(--pause-fg)", label: "Paused" },
    stop:    { fg: "var(--stop-fg)",  label: "Stopped" },
  }[status] || { fg: "var(--ink-400)", label: status };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, fontWeight: 700, color: m.fg,
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: 999, background: m.fg,
        animation: status === "running" ? "pulse 1.6s ease-in-out infinite" : "none",
      }} />
      {m.label}
    </span>
  );
};

window.Dashboard = Dashboard;
