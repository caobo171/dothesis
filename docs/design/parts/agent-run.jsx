// Live agent run — simple, doc-centered, OpenPaper-inspired.

const AgentRun = ({ go }) => {
  const { PHASES, AGENTS, CITATIONS } = window.DOTHESIS;

  // Phases
  const PHASE_ORDER = [
  { id: "research", label: "Research" },
  { id: "outline", label: "Outline" },
  { id: "writing", label: "Writing" },
  { id: "finalize", label: "Finalize" }];


  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1100);
    return () => clearInterval(id);
  }, []);

  const currentPhase = "research"; // mock: still researching
  const subTasks = [
  { id: "analyzing", label: "Analyzing", state: "active" },
  { id: "queries", label: "Queries", state: "queued" },
  { id: "search", label: "Search", state: "queued" },
  { id: "verify", label: "Verify", state: "queued" }];


  // sources accumulator
  const sourceCount = Math.min(8, Math.floor(tick / 3));
  const sourcesFound = CITATIONS.slice(0, sourceCount);

  const phaseAgents = {
    research: [
    { name: "Scout", role: "Searches academic databases" },
    { name: "Scribe", role: "Summarizes papers" },
    { name: "Signal", role: "Identifies research gaps" }]

  };

  return (
    <div className="canvas" style={{ padding: "0", gap: 0, background: "var(--ink-50)" }}>
      {/* Phase chips */}
      <div style={{
        background: "var(--paper)",
        borderBottom: "1px solid var(--ink-100)",
        padding: "16px 40px",
        display: "flex",
        justifyContent: "center",
        gap: 8
      }}>
        {PHASE_ORDER.map((p, i) => {
          const isCurrent = p.id === currentPhase;
          const isDone = PHASE_ORDER.findIndex((x) => x.id === currentPhase) > i;
          return (
            <React.Fragment key={p.id}>
              <div style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "8px 14px",
                borderRadius: 999,
                background: isCurrent ? "var(--ink-50)" : "transparent",
                fontWeight: 700, fontSize: 14,
                color: isCurrent ? "var(--ink-900)" : isDone ? "var(--ink-700)" : "var(--ink-400)"
              }}>
                {isCurrent ?
                <Spinner /> :
                isDone ?
                <Icon name="check" size={14} stroke={3} style={{ color: "var(--ok-fg)" }} /> :

                <span style={{
                  width: 14, height: 14, borderRadius: 999,
                  border: "1.5px solid var(--ink-300)"
                }} />
                }
                {p.label}
              </div>
              {i < PHASE_ORDER.length - 1 &&
              <span style={{
                width: 40, height: 1, alignSelf: "center",
                background: isDone ? "var(--ok-fg)" : "var(--ink-200)"
              }} />
              }
            </React.Fragment>);

        })}
      </div>

      {/* Two-column body */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 24, padding: "32px 40px 60px" }}>
        {/* Left: doc card */}
        <DocCard tick={tick} currentPhase={currentPhase} />

        {/* Right: panels */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <CurrentPhasePanel phase={currentPhase} subTasks={subTasks} />
          <SourcesPanel sources={sourcesFound} total={sourceCount} />
          <AgentTeamPanel agents={phaseAgents[currentPhase] || []} />
        </div>
      </div>

      {/* Quiet activity strip (collapsed by default) */}
      <ActivityStrip tick={tick} />
    </div>);

};

// ---------------- DocCard ----------------
const DocCard = ({ tick, currentPhase }) =>
<div style={{
  background: "var(--paper)",
  border: "1px solid var(--ink-100)",
  borderRadius: 16,
  padding: "48px 56px",
  boxShadow: "var(--shadow-card)"
}}>
    <div style={{
    textAlign: "center", letterSpacing: "0.18em",
    fontSize: 11, fontWeight: 700, color: "var(--ink-400)"
  }}>
      MASTER'S THESIS · POLITICAL SCIENCE
    </div>
    <h1 style={{
    fontFamily: "var(--font-serif)",
    fontSize: 28,
    fontWeight: 700,
    letterSpacing: "-0.01em",
    lineHeight: 1.25,
    textAlign: "center",
    margin: "22px 0 0",
    maxWidth: 620,
    marginLeft: "auto",
    marginRight: "auto"
  }}>
      Algorithmic Decision-Making and Democratic Accountability: A Comparative Study of EU and US Regulatory Frameworks
    </h1>

    <div style={{
    textAlign: "center",
    marginTop: 28,
    fontSize: 14,
    color: "var(--ink-500)",
    fontFamily: "var(--font-serif)",
    lineHeight: 1.9
  }}>
      <div>Master's Thesis Level</div>
      <div>APA 7th Format</div>
      <div>English</div>
      <div>May 23, 2026</div>
    </div>

    <div style={{ marginTop: 30, display: "flex", justifyContent: "center", alignItems: "center", gap: 8 }}>
      <Spinner />
      <span style={{ fontSize: 13.5, color: "var(--ink-500)", fontWeight: 600 }}>
        {currentPhase === "research" ? "Searching…" : "Working…"}
      </span>
    </div>

    {/* Step messages */}
    <div style={{ marginTop: 28, maxWidth: 520, marginLeft: "auto", marginRight: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
      <StepLine icon="sparkle" text="Identifying key concepts and terminology…" active />
      <StepLine icon="doc" text="Analyzing topic structure…" />
    </div>

    <div style={{ marginTop: 40 }}>
      <div className="eyebrow" style={{ textAlign: "center" }}>Sections being planned</div>
      <div style={{
      marginTop: 14, display: "grid",
      gridTemplateColumns: "1fr 1fr", gap: 10
    }}>
        {[0, 1, 2, 3, 4, 5].map((i) =>
      <div key={i} style={{
        height: 30,
        background: "var(--ink-50)",
        borderRadius: 8,
        position: "relative",
        overflow: "hidden"
      }}>
            <div style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(90deg, transparent, rgba(255,255,255,0.6), transparent)`,
          animation: `shimmer 1.6s ${i * 0.15}s ease-in-out infinite`
        }} />
          </div>
      )}
      </div>
    </div>

    <div style={{
    marginTop: 36, textAlign: "center",
    fontSize: 12, color: "var(--ink-400)"
  }}>
      You can close this tab. We'll email you when your paper is ready.
    </div>

    <style>{`
      @keyframes shimmer {
        0%   { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }
    `}</style>
  </div>;


const StepLine = ({ icon, text, active }) =>
<div style={{
  display: "flex", alignItems: "center", gap: 10,
  padding: "10px 14px",
  borderRadius: 10,
  background: active ? "var(--blue-50)" : "var(--ink-50)",
  color: active ? "var(--blue-600)" : "var(--ink-500)",
  fontSize: 13, fontWeight: 600
}}>
    <Icon name={icon} size={14} stroke={2} />
    {text}
  </div>;


// ---------------- Spinner ----------------
const Spinner = ({ size = 14 }) =>
<span style={{
  width: size, height: size, borderRadius: 999,
  border: "2px solid var(--blue-100)",
  borderTopColor: "var(--blue-600)",
  animation: "spin 0.8s linear infinite",
  display: "inline-block"
}}>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </span>;


// ---------------- Current phase panel ----------------
const CurrentPhasePanel = ({ phase, subTasks }) =>
<div style={{
  background: "var(--paper)",
  border: "1px solid var(--ink-100)",
  borderRadius: 14, padding: 18
}}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Spinner size={10} />
        <span style={{ fontSize: 14, fontWeight: 700 }}>
          Researching academic sources <span style={{ color: "var(--ink-500)", fontWeight: 600 }}>(Scout agent)…</span>
        </span>
      </div>
      <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 700 }}>0%</span>
    </div>
    <div style={{ display: "flex", gap: 6, marginTop: 14, flexWrap: "wrap" }}>
      {subTasks.map((s) =>
    <span key={s.id} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "5px 10px", borderRadius: 999,
      border: "1px solid var(--ink-200)",
      fontSize: 12, fontWeight: 600,
      color: s.state === "active" ? "var(--ink-900)" : "var(--ink-500)",
      background: s.state === "active" ? "var(--paper)" : "var(--paper)"
    }}>
          {s.state === "active" ? <Spinner size={9} /> :
      <span style={{ width: 8, height: 8, borderRadius: 999, border: "1.5px solid var(--ink-300)" }} />
      }
          {s.label}
        </span>
    )}
    </div>
    <div style={{
    marginTop: 14, fontSize: 12.5, color: "var(--ink-500)",
    display: "flex", justifyContent: "space-between"
  }}>
      <span>Preparing search queries</span>
      <span>Searching…</span>
    </div>
  </div>;


// ---------------- Sources panel ----------------
const SourcesPanel = ({ sources, total }) =>
<div style={{
  background: "var(--paper)",
  border: "1px solid var(--ink-100)",
  borderRadius: 14, padding: 18
}}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ fontSize: 14, fontWeight: 700 }}>Sources Found</div>
      {total > 0 &&
    <span style={{ fontSize: 12, color: "var(--blue-600)", fontWeight: 700 }}>
          {total} verified
        </span>
    }
    </div>
    {sources.length === 0 ?
  <div style={{
    marginTop: 14,
    padding: "32px 12px",
    textAlign: "center",
    background: "var(--ink-50)",
    borderRadius: 10,
    color: "var(--ink-400)",
    fontSize: 13
  }}>
        Searching for sources…
      </div> :

  <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {sources.map((s) =>
    <div key={s.key} className="fade-in" style={{
      padding: "10px 12px",
      background: "var(--ink-50)",
      borderRadius: 10,
      fontSize: 12.5
    }}>
            <div style={{
        fontFamily: "var(--font-serif)",
        fontWeight: 600,
        lineHeight: 1.3,
        color: "var(--ink-900)",
        overflow: "hidden",
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical"
      }}>{s.title}</div>
            <div style={{ marginTop: 4, color: "var(--ink-500)", fontSize: 11.5 }}>
              {s.authors.split(",")[0]} et al. · <span style={{ color: "var(--ok-fg)", fontWeight: 700 }}>✓ {s.source}</span>
            </div>
          </div>
    )}
      </div>
  }
  </div>;


// ---------------- Agent team panel ----------------
const AgentTeamPanel = ({ agents }) =>
<div style={{
  background: "var(--paper)",
  border: "1px solid var(--ink-100)",
  borderRadius: 14, padding: 18
}}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ fontSize: 14, fontWeight: 700 }}>Agent Team</div>
      <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 700 }}>
        {agents.length} active
      </span>
    </div>
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      {agents.map((a) =>
    <div key={a.name} style={{
      display: "flex", alignItems: "center", gap: 10,
      fontSize: 13
    }}>
          <span style={{
        width: 8, height: 8, borderRadius: 999,
        background: "var(--ok-fg)",
        boxShadow: "0 0 0 3px rgba(20, 133, 74, 0.18)"
      }} />
          <b style={{ color: "var(--ink-900)" }}>{a.name}</b>
          <span style={{ color: "var(--ink-500)" }}>{a.role}</span>
        </div>
    )}
    </div>
  </div>;


// ---------------- Activity strip (collapsed footer) ----------------
const ACTIVITY_LOG = [
  { t: "00:14", agent: "Scout",  text: "Queried Semantic Scholar for \"algorithmic accountability EU\"" },
  { t: "00:13", agent: "Scout",  text: "Queried CrossRef for \"AI Act Article 6 risk classification\"" },
  { t: "00:12", agent: "Signal", text: "Identified emerging trend — state-level US algorithmic accountability laws" },
  { t: "00:11", agent: "Scribe", text: "Summarized Floridi et al. (2022) — 412 words" },
  { t: "00:10", agent: "Scout",  text: "Fetched 6 sources from arXiv (query: enforcement asymmetry AI)" },
  { t: "00:09", agent: "Scout",  text: "Fetched 8 sources from Semantic Scholar (query: AI Act enforcement)" },
  { t: "00:08", agent: "Signal", text: "Identified research gap — comparative empirical work on enforcement asymmetry" },
  { t: "00:07", agent: "Scout",  text: "Discovered Veale & Borgesius (2021) via CrossRef" },
  { t: "00:06", agent: "Scribe", text: "Summarized Engstrom et al. (2020) — 358 words" },
  { t: "00:05", agent: "Scout",  text: "Discovered Wachter et al. (2023) via OpenAlex" },
  { t: "00:04", agent: "Scout",  text: "Discovered Smuha (2021) via Semantic Scholar" },
  { t: "00:03", agent: "Scout",  text: "Discovered Engstrom et al. (2020) via CrossRef" },
  { t: "00:02", agent: "Scout",  text: "Building search query plan from topic & research question" },
  { t: "00:01", agent: "System", text: "Pipeline started · Run #4821 · Claude Sonnet 4.5" },
];

const ActivityStrip = ({ tick }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      {open && (
        <div style={{
          borderTop: "1px solid var(--ink-100)",
          background: "var(--paper)",
          maxHeight: 280,
          overflowY: "auto",
        }} className="scroll">
          <div style={{
            padding: "10px 40px",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            borderBottom: "1px solid var(--ink-100)",
            position: "sticky", top: 0, background: "var(--paper)", zIndex: 1,
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-700)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Activity log · {ACTIVITY_LOG.length} events
            </div>
            <button
              className="btn btn-ghost btn-sm"
              style={{ padding: "4px 10px" }}
            >
              <Icon name="copy" size={12} /> Copy
            </button>
          </div>
          <div>
            {ACTIVITY_LOG.map((e, i) => (
              <div key={i} style={{
                display: "grid",
                gridTemplateColumns: "60px 90px 1fr",
                gap: 16,
                padding: "8px 40px",
                fontSize: 12.5,
                borderBottom: "1px solid var(--ink-50)",
              }}>
                <span style={{
                  fontFamily: "var(--font-mono)", color: "var(--ink-400)",
                }}>{e.t}</span>
                <span style={{
                  fontWeight: 700,
                  color: e.agent === "System" ? "var(--ink-500)" : "var(--blue-600)",
                }}>{e.agent}</span>
                <span style={{ color: "var(--ink-800)" }}>{e.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div style={{
        borderTop: "1px solid var(--ink-100)",
        background: "var(--paper)",
        padding: "10px 40px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        fontSize: 12.5,
      }}>
        <Spinner size={10} />
        <span style={{ color: "var(--ink-700)", fontWeight: 600 }}>
          Scout · just queried Semantic Scholar for "algorithmic accountability EU"
        </span>
        <span style={{ marginLeft: "auto", color: "var(--ink-400)", fontFamily: "var(--font-mono)" }}>
          00:{(tick % 60).toString().padStart(2, "0")}
        </span>
        <button onClick={() => setOpen((v) => !v)} style={{
          background: "none", border: "none", color: "var(--blue-600)",
          fontWeight: 700, cursor: "pointer", fontSize: 12.5,
          display: "inline-flex", alignItems: "center", gap: 4,
        }} data-comment-anchor="0b0494c609-button-382-7">
          {open ? "Hide log" : "View all activity"}
          <Icon name="chevron-down" size={12} stroke={2.5} style={{
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform 0.15s",
          }} />
        </button>
      </div>
    </>);
};

window.AgentRun = AgentRun;