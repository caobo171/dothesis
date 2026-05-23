"use client";

import { useEffect, useState } from "react";
import { Icon } from "./icons";
import { ProgressBar } from "./shared";
import { PHASES, AGENTS } from "./data";
import { openEventStream } from "../lib/api";

export const AgentRun = ({ jobId }) => {
  const [feed, setFeed] = useState([]);
  const [phaseStates, setPhaseStates] = useState({
    research: { state: "queued", progress: 0, activeAgents: [] },
    structure: { state: "queued", progress: 0, activeAgents: [] },
    compose: { state: "queued", progress: 0, activeAgents: [] },
    qa: { state: "queued", progress: 0, activeAgents: [] },
    compile: { state: "queued", progress: 0, activeAgents: [] },
    export: { state: "queued", progress: 0, activeAgents: [] },
  });
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!jobId) return;
    const close = openEventStream(jobId, {
      onEvent: (msg) => {
        if (msg.type === "activity") {
          setFeed((f) => [{ phase: msg.phase || "compose", agent: msg.agent || "Engine",
                            text: msg.text || "", t: new Date().toLocaleTimeString().slice(0, 5) }, ...f].slice(0, 50));
        } else if (msg.type === "phase_progress") {
          setPhaseStates((prev) => {
            const next = { ...prev };
            const order = ["research", "structure", "compose", "qa", "compile", "export"];
            const idx = order.indexOf(msg.phase);
            for (let i = 0; i < idx; i++) next[order[i]] = { ...next[order[i]], state: "done", progress: 1, activeAgents: [] };
            next[msg.phase] = { state: msg.progress >= 1 ? "done" : "active",
                                 progress: msg.progress || 0,
                                 activeAgents: msg.active_agents || [] };
            return next;
          });
        }
      },
      onDone: () => setDone(true),
      onError: (e) => setError(e.text || e.message || "stream error"),
    });
    return close;
  }, [jobId]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1100);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="canvas" style={{ gap: 20 }}>
      {error && (
        <div style={{ padding: "12px 16px", background: "var(--danger-bg, #fde2e2)", color: "var(--danger-fg, #b91c1c)",
                       borderRadius: 8, fontSize: 13, fontWeight: 600 }}>
          Job failed: {error}
        </div>
      )}
      {done && (
        <div style={{ padding: "12px 16px", background: "var(--ok-bg, #d1fae5)", color: "var(--ok-fg, #047857)",
                       borderRadius: 8, fontSize: 13, fontWeight: 600 }}>
          Draft ready — open the Editor tab.
        </div>
      )}
      <PipelineDiagram phaseStates={phaseStates} tick={tick} />
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 20 }}>
        <ActivityFeed feed={feed} />
        <ChapterProgress />
      </div>
      <CitationStream />
    </div>
  );
};

const LegendDot = ({ color, label, pulse }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
    <span style={{
      width: 8, height: 8, borderRadius: 999, background: color,
      boxShadow: pulse ? `0 0 0 4px ${color}22` : "none",
    }} />
    {label}
  </span>
);

const PipelineDiagram = ({ phaseStates, tick }) => (
  <div className="card" style={{ padding: 0, overflow: "hidden" }}>
    <div className="card-header">
      <div>
        <div className="section-title">19 agents · 6 phases</div>
        <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 4 }}>
          Hover any agent to see what it&apos;s doing. Data flows left to right.
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12, color: "var(--ink-500)", fontWeight: 600 }}>
        <LegendDot color="var(--ok-fg)" label="Done" />
        <LegendDot color="var(--blue-600)" label="Active" pulse />
        <LegendDot color="var(--ink-300)" label="Queued" />
      </div>
    </div>

    <div style={{ padding: "32px 28px 28px", position: "relative" }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(6, 1fr)",
        gap: 0,
        position: "relative",
      }}>
        {PHASES.map((p, i) => (
          <PhaseColumn
            key={p.id}
            phase={p}
            state={phaseStates[p.id]}
            agents={AGENTS.filter((a) => a.phase === p.id)}
            activeAgents={phaseStates[p.id].activeAgents}
            isFirst={i === 0}
            isLast={i === PHASES.length - 1}
            tick={tick}
          />
        ))}
        {PHASES.slice(0, -1).map((p, i) => {
          const fromState = phaseStates[p.id].state;
          const active = fromState === "done" || fromState === "active";
          if (!active) return null;
          return <FlowParticles key={i} index={i} color={p.color} />;
        })}
      </div>
    </div>
  </div>
);

const PHASE_NUMBERS = ["1", "2", "3", "3.5", "4", "5"];
const PHASE_ORDER = ["research", "structure", "compose", "qa", "compile", "export"];

const PhaseColumn = ({ phase, state, agents, activeAgents, isFirst, tick }) => {
  const isDone = state.state === "done";
  const isActive = state.state === "active";
  const isQueued = state.state === "queued";
  const stateColor = isDone ? "var(--ok-fg)" : isActive ? phase.color : "var(--ink-300)";

  return (
    <div style={{
      padding: "0 12px",
      borderLeft: isFirst ? "none" : "1px dashed var(--ink-200)",
      position: "relative",
    }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 8, marginBottom: 16 }}>
        <div style={{
          width: 42, height: 42, borderRadius: 12,
          background: isQueued ? "var(--ink-50)" : `${phase.color}15`,
          color: isQueued ? "var(--ink-400)" : phase.color,
          display: "grid", placeItems: "center",
          border: isActive ? `2px solid ${phase.color}` : "2px solid transparent",
          boxShadow: isActive ? `0 0 0 4px ${phase.color}20` : "none",
        }}>
          <Icon name={phase.icon} size={22} />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 10.5, color: "var(--ink-400)", fontWeight: 700,
                           letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Phase {PHASE_NUMBERS[PHASE_ORDER.indexOf(phase.id)]}
            </span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 16, marginTop: 2, color: "var(--ink-900)" }}>
            {phase.label}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--ink-500)", marginTop: 2, lineHeight: 1.35 }}>
            {phase.desc}
          </div>
        </div>
        <div style={{ width: "100%" }}>
          <ProgressBar value={state.progress} color={stateColor} height={4} />
          <div style={{ marginTop: 6, display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700 }}>
            <span style={{ color: stateColor }}>
              {isDone ? "Complete" : isActive ? `${Math.round(state.progress * 100)}%` : "Queued"}
            </span>
            <span style={{ color: "var(--ink-400)" }}>{agents.length} agents</span>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {agents.map((a) => {
          const isAgentActive = activeAgents.includes(a.name);
          return (
            <AgentChip
              key={a.name}
              agent={a}
              phase={phase}
              status={
                isDone ? "done" :
                isAgentActive ? "active" :
                "queued"
              }
              tick={tick}
            />
          );
        })}
      </div>
    </div>
  );
};

const AgentChip = ({ agent, phase, status, tick }) => {
  const isActive = status === "active";
  const isDone = status === "done";
  const isQueued = status === "queued";
  const [hover, setHover] = useState(false);

  const bg = isActive ? phase.color : "var(--paper)";
  const fg = isActive ? "white" : isDone ? "var(--ink-700)" : "var(--ink-400)";
  const border = isActive ? phase.color : "var(--ink-100)";

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "relative",
        padding: "8px 10px",
        borderRadius: 10,
        background: bg,
        color: fg,
        border: `1px solid ${border}`,
        fontSize: 12,
        fontWeight: 600,
        display: "flex",
        alignItems: "center",
        gap: 6,
        opacity: isQueued ? 0.55 : 1,
        cursor: "default",
      }}
    >
      <span style={{
        width: 7, height: 7, borderRadius: 999,
        background: isActive ? "white" : isDone ? "var(--ok-fg)" : "var(--ink-300)",
        boxShadow: isActive ? `0 0 0 ${tick % 2 === 0 ? 3 : 1}px rgba(255,255,255,0.4)` : "none",
        transition: "box-shadow 0.4s ease",
        flexShrink: 0,
      }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {agent.name}
      </span>
      {isActive && (
        <span style={{
          marginLeft: "auto", fontSize: 9, fontWeight: 800,
          padding: "2px 6px", borderRadius: 4,
          background: "rgba(255,255,255,0.2)", letterSpacing: 0.4,
        }}>WORKING</span>
      )}
      {isDone && (
        <Icon name="check" size={12} stroke={3} style={{ color: "var(--ok-fg)", marginLeft: "auto" }} />
      )}
      {hover && (
        <div className="tooltip" style={{ top: -34, left: 0, zIndex: 100 }}>
          {agent.role}
        </div>
      )}
    </div>
  );
};

const FlowParticles = ({ index, color }) => {
  const left = `${((index + 1) / 6) * 100}%`;
  return (
    <div style={{
      position: "absolute",
      top: 20,
      left,
      transform: "translateX(-50%)",
      width: 40,
      height: 30,
      pointerEvents: "none",
      zIndex: 1,
    }}>
      {[0, 0.5, 1.0].map((delay, i) => (
        <span key={i} style={{
          position: "absolute",
          top: 12,
          left: -20,
          width: 6, height: 6,
          borderRadius: 999,
          background: color,
          boxShadow: `0 0 8px ${color}`,
          animation: `particleFlow 1.8s ${delay}s linear infinite`,
        }} />
      ))}
    </div>
  );
};

const ActivityFeed = ({ feed }) => {
  const phaseById = Object.fromEntries(PHASES.map((p) => [p.id, p]));
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div className="card-header">
        <div>
          <div className="section-title">Live activity</div>
          <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 3 }}>What the agents just did — newest first.</div>
        </div>
        <button className="btn btn-ghost btn-sm">
          <Icon name="copy" size={12} /> Export log
        </button>
      </div>
      <div className="scroll" style={{ maxHeight: 420, overflowY: "auto" }}>
        {feed.map((f, i) => {
          const p = phaseById[f.phase];
          return (
            <div key={i} className="fade-in" style={{
              padding: "14px 24px",
              display: "grid",
              gridTemplateColumns: "60px 1fr auto",
              gap: 16,
              borderBottom: "1px solid var(--ink-100)",
              alignItems: "center",
            }}>
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                color: "var(--ink-400)",
                fontWeight: 500,
              }}>
                {f.t}
              </span>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    color: p.color,
                    padding: "1px 8px",
                    background: `${p.color}15`,
                    borderRadius: 999,
                  }}>
                    {f.agent}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: "var(--ink-800)", lineHeight: 1.4 }}>{f.text}</div>
              </div>
              <Icon name="check" size={14} stroke={3} style={{ color: "var(--ok-fg)" }} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ChapterProgress = () => (
  <div className="card" style={{ overflow: "hidden" }}>
    <div className="card-header">
      <div>
        <div className="section-title">Chapter progress</div>
        <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 3 }}>Per-chapter detail available after the job finishes.</div>
      </div>
      <span className="badge run"><span className="pulse" />Compose · QA</span>
    </div>
    <div style={{ padding: "24px", fontSize: 13, color: "var(--ink-500)" }}>
      Drafting in progress — chapter detail coming once the job finishes.
    </div>
  </div>
);

const CitationStream = () => (
  <div className="card" style={{ overflow: "hidden" }}>
    <div className="card-header">
      <div>
        <div className="section-title">Citation verification stream</div>
        <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 3 }}>
          Every source checked against CrossRef, OpenAlex, Semantic Scholar and arXiv before it makes the bibliography.
        </div>
      </div>
    </div>
    <div style={{ padding: "24px", fontSize: 13, color: "var(--ink-500)" }}>
      Citations will appear here once the job finishes.
    </div>
  </div>
);

