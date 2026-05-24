"use client";

import { useEffect, useState } from "react";
import { Icon } from "./icons";
import { Spinner } from "./shared";
import { openEventStream } from "../lib/api";

const PHASE_ORDER = [
  { id: "research", label: "Research" },
  { id: "structure", label: "Outline" },
  { id: "compose", label: "Writing" },
  { id: "qa", label: "Review" },
  { id: "compile", label: "Compile" },
  { id: "export", label: "Export" },
];

const PHASE_ID_BY_BACKEND = {
  research: "research",
  structure: "structure",
  compose: "compose",
  qa: "qa",
  compile: "compile",
  export: "export",
  // The engine sometimes uses these synonyms — normalize.
  exporting: "export",
  writing: "compose",
  completed: "export",
};

export const AgentRun = ({ jobId, paper }) => {
  const [activity, setActivity] = useState([]); // newest first, capped
  const [sources, setSources] = useState([]); // citation-like events
  const [currentPhase, setCurrentPhase] = useState("research");
  const [phaseProgress, setPhaseProgress] = useState({}); // {phaseId: 0..1}
  const [activeAgents, setActiveAgents] = useState([]);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [startedAt] = useState(() => Date.now());
  const [lastUpdate, setLastUpdate] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const close = openEventStream(jobId, {
      onEvent: (msg) => {
        setLastUpdate(Date.now());
        if (msg.type === "phase_progress") {
          const id = PHASE_ID_BY_BACKEND[msg.phase] || msg.phase;
          setCurrentPhase(id);
          setPhaseProgress((p) => ({ ...p, [id]: msg.progress || 0 }));
          if (Array.isArray(msg.active_agents)) setActiveAgents(msg.active_agents);
        } else if (msg.type === "activity") {
          const phase = PHASE_ID_BY_BACKEND[msg.phase] || msg.phase || currentPhase;
          setActivity((a) =>
            [
              {
                phase,
                agent: msg.agent || "Engine",
                text: msg.text || "",
                t: new Date().toLocaleTimeString().slice(0, 8),
              },
              ...a,
            ].slice(0, 100),
          );
          if (msg.source && typeof msg.source === "object") {
            const s = msg.source;
            setSources((cur) =>
              cur.some((x) => x.title === s.title)
                ? cur
                : [
                    {
                      title: s.title,
                      authors: s.authors || "",
                      year: s.year,
                      doi: s.doi || null,
                      url: s.url || null,
                      venue: s.venue || s.journal || null,
                      source: msg.agent || "verified",
                    },
                    ...cur,
                  ].slice(0, 50),
            );
          }
        }
      },
      onDone: () => setDone(true),
      onError: (e) => {
        // Transient blips are auto-recovered by EventSource — ignore them.
        if (e.transient) return;
        setError(e.text || e.message || "stream error");
      },
    });
    return close;
  }, [jobId]);

  const currentLabel = PHASE_ORDER.find((p) => p.id === currentPhase)?.label || "Research";
  const elapsedSec = Math.floor((now - startedAt) / 1000);
  const sinceUpdateSec = Math.floor((now - lastUpdate) / 1000);
  const stalled = sinceUpdateSec > 25 && !done && !error;

  return (
    <div className="canvas" style={{ padding: 0, gap: 0, background: "var(--ink-50)" }}>
      {/* Phase chips */}
      <PhaseChips currentPhase={currentPhase} phaseProgress={phaseProgress} done={done} />

      {/* Banners */}
      {error && (
        <div
          style={{
            margin: "16px 40px 0",
            padding: "12px 16px",
            background: "var(--stop-bg)",
            color: "var(--stop-fg)",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Job failed: {error}
        </div>
      )}
      {done && (
        <div
          style={{
            margin: "16px 40px 0",
            padding: "12px 16px",
            background: "var(--ok-bg)",
            color: "var(--ok-fg)",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Draft ready — open the Draft tab.
        </div>
      )}

      {/* Two-column body */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          gap: 24,
          padding: "32px 40px 24px",
        }}
      >
        <DocCard
          currentPhase={currentPhase}
          currentLabel={currentLabel}
          paper={paper}
          done={done}
          error={error}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <CurrentPhasePanel
            currentLabel={currentLabel}
            progress={phaseProgress[currentPhase] || 0}
            agents={activeAgents}
            elapsedSec={elapsedSec}
            sinceUpdateSec={sinceUpdateSec}
            stalled={stalled}
          />
          <SourcesPanel sources={sources} />
          <RecentActivityPanel activity={activity} />
        </div>
      </div>

      {/* Tail activity strip */}
      <ActivityStrip activity={activity} />
    </div>
  );
};

// ---------------- Phase chips ----------------
const PhaseChips = ({ currentPhase, phaseProgress, done }) => {
  const currentIdx = PHASE_ORDER.findIndex((p) => p.id === currentPhase);
  return (
    <div
      style={{
        background: "var(--paper)",
        borderBottom: "1px solid var(--ink-100)",
        padding: "16px 40px",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: 8,
        flexWrap: "wrap",
      }}
    >
      {PHASE_ORDER.map((p, i) => {
        const isCurrent = !done && p.id === currentPhase;
        const isDoneStep = done || currentIdx > i;
        return (
          <span key={p.id} style={{ display: "inline-flex", alignItems: "center" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 14px",
                borderRadius: 999,
                background: isCurrent ? "var(--ink-50)" : "transparent",
                fontWeight: 700,
                fontSize: 14,
                color: isCurrent
                  ? "var(--ink-900)"
                  : isDoneStep
                  ? "var(--ink-700)"
                  : "var(--ink-400)",
              }}
            >
              {isCurrent ? (
                <Spinner />
              ) : isDoneStep ? (
                <Icon name="check" size={14} stroke={3} style={{ color: "var(--ok-fg)" }} />
              ) : (
                <span
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 999,
                    border: "1.5px solid var(--ink-300)",
                  }}
                />
              )}
              {p.label}
            </span>
            {i < PHASE_ORDER.length - 1 && (
              <span
                style={{
                  width: 24,
                  height: 1,
                  background: isDoneStep ? "var(--ok-fg)" : "var(--ink-200)",
                }}
              />
            )}
          </span>
        );
      })}
    </div>
  );
};

// ---------------- DocCard ----------------
const DocCard = ({ currentPhase, currentLabel, paper, done, error }) => (
  <div
    style={{
      background: "var(--paper)",
      border: "1px solid var(--ink-100)",
      borderRadius: 16,
      padding: "48px 56px",
      boxShadow: "var(--shadow-card)",
    }}
  >
    <div
      style={{
        textAlign: "center",
        letterSpacing: "0.18em",
        fontSize: 11,
        fontWeight: 700,
        color: "var(--ink-400)",
      }}
    >
      {(paper?.level || "Master's thesis").toUpperCase()}
    </div>
    <h1
      style={{
        fontFamily: "var(--font-serif)",
        fontSize: 28,
        fontWeight: 700,
        letterSpacing: "-0.01em",
        lineHeight: 1.25,
        textAlign: "center",
        margin: "22px auto 0",
        maxWidth: 620,
      }}
    >
      {paper?.title || "Untitled thesis"}
    </h1>

    {!done && !error && (
      <>
        <div
          style={{
            marginTop: 30,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: 8,
          }}
        >
          <Spinner />
          <span style={{ fontSize: 13.5, color: "var(--ink-500)", fontWeight: 600 }}>
            {currentLabel}…
          </span>
        </div>

        <div style={{ marginTop: 40 }}>
          <div className="eyebrow" style={{ textAlign: "center" }}>
            Sections being prepared
          </div>
          <div
            style={{
              marginTop: 14,
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 10,
            }}
          >
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                style={{
                  height: 30,
                  background: "var(--ink-50)",
                  borderRadius: 8,
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background:
                      "linear-gradient(90deg, transparent, rgba(255,255,255,0.6), transparent)",
                    animation: `shimmer 1.6s ${i * 0.15}s ease-in-out infinite`,
                  }}
                />
              </div>
            ))}
          </div>
        </div>

        <div
          style={{
            marginTop: 36,
            textAlign: "center",
            fontSize: 12,
            color: "var(--ink-400)",
          }}
        >
          Generation takes 10–20 minutes. You can leave this tab open.
        </div>

        <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }`}</style>
      </>
    )}

    {done && (
      <div style={{ marginTop: 28, textAlign: "center" }}>
        <Icon name="checkcircle" size={48} stroke={1.5} style={{ color: "var(--ok-fg)" }} />
        <div style={{ marginTop: 12, fontSize: 16, fontWeight: 700, color: "var(--ink-900)" }}>
          Draft complete
        </div>
        <div style={{ marginTop: 4, fontSize: 13, color: "var(--ink-500)" }}>
          Open the Draft, Citations, or Export tabs.
        </div>
      </div>
    )}

    {error && (
      <div style={{ marginTop: 28, textAlign: "center" }}>
        <Icon name="warning" size={48} stroke={1.5} style={{ color: "var(--stop-fg)" }} />
        <div style={{ marginTop: 12, fontSize: 16, fontWeight: 700, color: "var(--stop-fg)" }}>
          Generation failed
        </div>
        <div
          style={{
            marginTop: 4,
            fontSize: 13,
            color: "var(--ink-500)",
            maxWidth: 480,
            margin: "8px auto 0",
          }}
        >
          {error}
        </div>
      </div>
    )}
  </div>
);

// ---------------- Current phase panel ----------------
const fmtTime = (sec) => {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
};

const CurrentPhasePanel = ({ currentLabel, progress, agents, elapsedSec, sinceUpdateSec, stalled }) => (
  <div
    style={{
      background: "var(--paper)",
      border: "1px solid var(--ink-100)",
      borderRadius: 14,
      padding: 18,
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Spinner size={10} />
        <span style={{ fontSize: 14, fontWeight: 700 }}>
          {currentLabel}{" "}
          {agents.length > 0 && (
            <span style={{ color: "var(--ink-500)", fontWeight: 600 }}>
              ({agents.join(", ")})
            </span>
          )}
        </span>
      </div>
      <span style={{ fontSize: 12, color: "var(--ink-400)", fontWeight: 700 }}>
        {Math.round((progress || 0) * 100)}%
      </span>
    </div>
    {/* Progress bar: shimmer when nothing's coming in, solid otherwise. */}
    <div
      style={{
        marginTop: 14,
        height: 4,
        borderRadius: 999,
        background: "var(--ink-100)",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          width: `${Math.max(2, Math.round((progress || 0) * 100))}%`,
          height: "100%",
          background: "var(--blue-600)",
          transition: "width 0.4s ease",
          opacity: stalled ? 0.4 : 1,
        }}
      />
      {stalled && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(90deg, transparent 0%, rgba(28,46,255,0.45) 50%, transparent 100%)",
            animation: "indeterminate 1.6s ease-in-out infinite",
          }}
        />
      )}
    </div>
    {/* Heartbeat row: elapsed + last-update */}
    <div
      style={{
        marginTop: 10,
        display: "flex",
        justifyContent: "space-between",
        fontSize: 11.5,
        color: "var(--ink-500)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      <span>
        Elapsed <b style={{ color: "var(--ink-700)" }}>{fmtTime(elapsedSec)}</b>
      </span>
      <span style={{ color: stalled ? "var(--pause-fg)" : "var(--ink-500)" }}>
        {stalled
          ? `Quiet for ${fmtTime(sinceUpdateSec)} (upstream APIs may be throttling — engine still alive)`
          : `Updated ${fmtTime(sinceUpdateSec)} ago`}
      </span>
    </div>
    <style>{`@keyframes indeterminate { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }`}</style>
  </div>
);

// ---------------- Sources panel ----------------
function sourceHref(s) {
  if (s.url) return s.url;
  if (s.doi) {
    const doi = String(s.doi).trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
    return `https://doi.org/${doi}`;
  }
  // Fall back to a Google Scholar lookup so the citation is at least one click from verifiable
  return `https://scholar.google.com/scholar?q=${encodeURIComponent(s.title || "")}`;
}

const SourceRow = ({ s }) => (
  <a
    href={sourceHref(s)}
    target="_blank"
    rel="noopener noreferrer"
    className="fade-in source-row"
    style={{
      display: "block",
      padding: "10px 12px",
      background: "var(--ink-50)",
      borderRadius: 10,
      fontSize: 12.5,
      textDecoration: "none",
      color: "inherit",
      transition: "background 0.12s, transform 0.12s",
    }}
    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--blue-50)"; }}
    onMouseLeave={(e) => { e.currentTarget.style.background = "var(--ink-50)"; }}
    title={s.doi ? `DOI: ${s.doi}` : s.url || "Open in Google Scholar"}
  >
    <div
      style={{
        fontFamily: "var(--font-serif)",
        fontWeight: 600,
        lineHeight: 1.3,
        color: "var(--ink-900)",
        overflow: "hidden",
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
      }}
    >
      {s.title}
    </div>
    <div
      style={{
        marginTop: 4,
        color: "var(--ink-500)",
        fontSize: 11.5,
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <span>
        {s.authors?.split(",")[0] || "—"}
        {s.year ? `, ${s.year}` : ""}
      </span>
      {s.doi && (
        <span style={{ color: "var(--blue-600)", fontWeight: 700 }}>· DOI</span>
      )}
      {!s.doi && !s.url && (
        <span style={{ color: "var(--ink-400)", fontWeight: 600 }}>· Scholar</span>
      )}
    </div>
  </a>
);

const SourcesPanel = ({ sources }) => (
  <div
    style={{
      background: "var(--paper)",
      border: "1px solid var(--ink-100)",
      borderRadius: 14,
      padding: 18,
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ fontSize: 14, fontWeight: 700 }}>Sources Found</div>
      {sources.length > 0 && (
        <span style={{ fontSize: 12, color: "var(--blue-600)", fontWeight: 700 }}>
          {sources.length} verified
        </span>
      )}
    </div>
    {sources.length === 0 ? (
      <div
        style={{
          marginTop: 14,
          padding: "32px 12px",
          textAlign: "center",
          background: "var(--ink-50)",
          borderRadius: 10,
          color: "var(--ink-400)",
          fontSize: 13,
        }}
      >
        Searching for sources…
      </div>
    ) : (
      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {sources.slice(0, 8).map((s, i) => (
          <SourceRow key={s.title + i} s={s} />
        ))}
      </div>
    )}
  </div>
);

const RecentActivityPanel = ({ activity }) => (
  <div
    style={{
      background: "var(--paper)",
      border: "1px solid var(--ink-100)",
      borderRadius: 14,
      padding: 18,
    }}
  >
    <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Recent activity</div>
    {activity.length === 0 ? (
      <div style={{ fontSize: 13, color: "var(--ink-400)" }}>Waiting for the engine…</div>
    ) : (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          maxHeight: 220,
          overflowY: "auto",
        }}
        className="scroll"
      >
        {activity.slice(0, 12).map((e, i) => (
          <div
            key={i}
            style={{
              fontSize: 12.5,
              color: "var(--ink-700)",
              padding: "6px 0",
              borderBottom: i < 11 ? "1px solid var(--ink-50)" : "none",
            }}
          >
            <span style={{ color: "var(--blue-600)", fontWeight: 700 }}>{e.agent}</span>{" "}
            <span style={{ color: "var(--ink-500)" }}>{e.text}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);

// ---------------- Activity strip (tail) ----------------
const ActivityStrip = ({ activity }) => {
  const [open, setOpen] = useState(false);
  const latest = activity[0];
  return (
    <>
      {open && (
        <div
          style={{
            borderTop: "1px solid var(--ink-100)",
            background: "var(--paper)",
            maxHeight: 320,
            overflowY: "auto",
          }}
          className="scroll"
        >
          <div
            style={{
              padding: "10px 40px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderBottom: "1px solid var(--ink-100)",
              position: "sticky",
              top: 0,
              background: "var(--paper)",
              zIndex: 1,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: "var(--ink-700)",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
              }}
            >
              Activity log · {activity.length} events
            </div>
          </div>
          <div>
            {activity.map((e, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "70px 90px 1fr",
                  gap: 16,
                  padding: "8px 40px",
                  fontSize: 12.5,
                  borderBottom: "1px solid var(--ink-50)",
                }}
              >
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--ink-400)" }}>
                  {e.t}
                </span>
                <span style={{ fontWeight: 700, color: "var(--blue-600)" }}>{e.agent}</span>
                <span style={{ color: "var(--ink-800)" }}>{e.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div
        style={{
          borderTop: "1px solid var(--ink-100)",
          background: "var(--paper)",
          padding: "10px 40px",
          display: "flex",
          alignItems: "center",
          gap: 12,
          fontSize: 12.5,
        }}
      >
        <Spinner size={10} />
        <span
          style={{
            color: "var(--ink-700)",
            fontWeight: 600,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {latest ? `${latest.agent} · ${latest.text}` : "Waiting for engine…"}
        </span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          style={{
            background: "none",
            border: "none",
            color: "var(--blue-600)",
            fontWeight: 700,
            cursor: "pointer",
            fontSize: 12.5,
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          {open ? "Hide log" : "View all"}
          <Icon
            name="chevron-down"
            size={12}
            stroke={2.5}
            style={{
              transform: open ? "rotate(180deg)" : "none",
              transition: "transform 0.15s",
            }}
          />
        </button>
      </div>
    </>
  );
};
