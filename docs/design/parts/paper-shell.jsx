// PaperShell — minimal: title bar + 4 tabs, that's it.

const PaperShell = ({ go, paper, tab, setTab, children }) => {
  const tabs = [
    { id: "run",       label: "Generation" },
    { id: "editor",    label: "Draft" },
    { id: "citations", label: "Citations" },
    { id: "export",    label: "Export" },
  ];

  const statusLabel = {
    running: "Generating",
    ok: "Complete",
    pause: "Paused",
    stop: "Stopped",
  }[paper.status] || "";
  const statusColor = {
    running: "var(--blue-600)",
    ok: "var(--ok-fg)",
    pause: "var(--pause-fg)",
    stop: "var(--stop-fg)",
  }[paper.status] || "var(--ink-400)";

  return (
    <div className="main">
      <div style={{
        background: "var(--paper)",
        borderBottom: "1px solid var(--ink-100)",
        padding: "16px 40px 0",
      }}>
        {/* Title row */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 36 }}>
          <button
            onClick={() => go("dashboard")}
            style={{
              padding: "6px 8px", border: "none", background: "transparent",
              color: "var(--ink-500)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
              fontSize: 13, fontWeight: 600, borderRadius: 8,
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = "var(--ink-50)"}
            onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
          >
            <Icon name="arrow-left" size={14} />
          </button>
          <div style={{
            flex: 1, minWidth: 0,
            fontFamily: "var(--font-serif)",
            fontSize: 17,
            fontWeight: 600,
            letterSpacing: "-0.005em",
            color: "var(--ink-900)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {paper.title}
          </div>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontSize: 12.5, fontWeight: 700, color: statusColor,
            flexShrink: 0,
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: 999, background: statusColor,
              animation: paper.status === "running" ? "pulse 1.6s ease-in-out infinite" : "none",
            }} />
            {statusLabel}
          </span>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginTop: 14 }}>
          {tabs.map((tb) => (
            <button
              key={tb.id}
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
                <span style={{
                  position: "absolute",
                  left: 12, right: 12, bottom: -1, height: 2,
                  background: "var(--blue-600)",
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

window.PaperShell = PaperShell;
