/** Core features — jenni-style: alternating rows, each with a looping,
 *  JS-driven demo of the actual feature rather than a static mockup. */
"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { AssistantTurn, Badge, CitationChip } from "./ds";
import { IconArrow, IconCheck, SectionHead, Reveal } from "./shared";


// One shared clock for every demo: advance a step every `ms`, wrapping at
// `count`. Parked entirely for reduced-motion users, who then see the demo's
// resting state (the last step) rather than a frozen mid-animation frame.
function useCycle(count: number, ms: number): number {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (typeof window !== "undefined"
        && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setI(count - 1);
      return;
    }
    const id = setInterval(() => setI(x => (x + 1) % count), ms);
    return () => clearInterval(id);
  }, [count, ms]);
  return i;
}


function MockShell({ label, children, pad = 22 }: {
  label: string; children: ReactNode; pad?: number;
}) {
  return (
    <div style={{
      background: "#fff", border: "1px solid var(--ink-200)", borderRadius: 18,
      boxShadow: "var(--shadow-card)", overflow: "hidden",
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
        borderBottom: "1px solid var(--ink-100)", background: "var(--ink-50)",
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          {[0, 1, 2].map(i => (
            <span key={i} style={{ width: 9, height: 9, borderRadius: 999, background: "var(--ink-200)" }} />
          ))}
        </div>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-500)", marginLeft: 4 }}>
          {label}
        </span>
      </div>
      <div style={{ padding: pad }}>{children}</div>
    </div>
  );
}


// A pale ring that pulses onto whichever citation is being checked this tick.
function Checking({ on, children }: { on: boolean; children: ReactNode }) {
  return (
    <span style={{
      borderRadius: 6,
      boxShadow: on ? "0 0 0 3px var(--primary-100)" : "0 0 0 0 transparent",
      background: on ? "var(--primary-50)" : "transparent",
      transition: "box-shadow .3s, background .3s",
    }}>
      {children}
    </span>
  );
}

// VERIFIED CITATIONS — the checker sweeps each cited claim, then flips the badge
// to "100% verified" before looping.
function CitationsMock() {
  const step = useCycle(3, 1500); // 0 → chip A, 1 → chip B, 2 → all verified
  const verified = step === 2;
  return (
    <MockShell label="Literature Review · M2">
      <AssistantTurn module="M2" footer={
        <>
          <button type="button" className="ds-ghost-action">⧉ Copy</button>
          <span style={{ fontSize: 11.5, color: "var(--ink-400)" }}>APA 7</span>
        </>
      }>
        <p>
          The enforcement asymmetry between EU and US regulators is well documented{" "}
          <Checking on={step === 0}>
            <CitationChip label="Nguyen 2021" title="Algorithmic accountability across jurisdictions"
              url="https://doi.org/10.1016/j.chb.2021.106789" />
          </Checking>
          , though a shared accountability metric is still missing{" "}
          <Checking on={step === 1}>
            <CitationChip label="Okafor 2023" title="Toward measurable AI accountability"
              url="https://doi.org/10.1145/3593013" />
          </Checking>.
        </p>
      </AssistantTurn>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
        <Badge tone={verified ? "ok" : "idle"}>{verified ? "100% verified" : "Verifying…"}</Badge>
        <span style={{ fontSize: 12.5, color: "var(--ink-500)" }}>checked against CrossRef</span>
      </div>
    </MockShell>
  );
}


// A real PDF file icon (white page, red "PDF" tab) instead of a plain text pill.
function PdfIcon() {
  return (
    <svg width="30" height="30" viewBox="0 0 24 24" aria-hidden style={{ flexShrink: 0 }}>
      <rect x="4" y="2" width="16" height="20" rx="2.5" fill="#fff" stroke="#E04A3F" strokeWidth="1.4" />
      <rect x="5.6" y="13.4" width="12.8" height="7" rx="1.6" fill="#E04A3F" />
      <text x="12" y="18.2" textAnchor="middle" fontSize="5.4" fontWeight="800" fill="#fff"
        style={{ fontFamily: "var(--font-sans)" }}>PDF</text>
    </svg>
  );
}

// SOURCE-GROUNDED — a reading cursor moves down your library; each paper it
// passes flips to "Cited", then the loop restarts.
function SourcesMock() {
  const rows: Array<[string, string]> = [
    ["Algorithmic accountability across jurisdictions", "Nguyen, Tran · 2021"],
    ["Toward measurable AI accountability", "Okafor, Blau · 2023"],
    ["Regulatory divergence in AI governance", "Schmidt et al. · 2022"],
  ];
  const step = useCycle(rows.length + 1, 1100); // 0..len; row < step = cited, == step = reading
  return (
    <MockShell label="Your library · 14 sources" pad={16}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {rows.map(([title, authors], i) => {
          const reading = i === step;
          const cited = i < step;
          return (
            <div key={title} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
              border: `1px solid ${reading ? "var(--primary-500)" : "var(--ink-200)"}`,
              background: reading ? "var(--primary-50)" : "#fff",
              borderRadius: 12, transition: "border-color .3s, background .3s",
            }}>
              <PdfIcon />
              <div style={{ minWidth: 0 }}>
                <div className="lp-serif" style={{
                  fontSize: 13.5, fontWeight: 700, color: "var(--ink-800)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>{title}</div>
                <div style={{ fontSize: 12, color: "var(--ink-500)" }}>{authors}</div>
              </div>
              <span style={{ marginLeft: "auto", flexShrink: 0, opacity: cited || reading ? 1 : 0.35, transition: "opacity .3s" }}>
                <Badge tone={cited ? "ok" : "idle"}>{cited ? "Cited" : reading ? "Reading…" : "Queued"}</Badge>
              </span>
            </div>
          );
        })}
      </div>
    </MockShell>
  );
}


// CONTEXT STORE — a live memory in plain language (NOT raw JSON, which read as
// developer tooling): labelled rows a student understands, with the verified
// count ticking up and the status flipping as the agent commits, on a loop.
function ContextMock() {
  const step = useCycle(3, 1500); // sources 12→13→14, status flips at the end
  const done = step === 2;
  const Row = ({ label, children }: { label: string; children: ReactNode }) => (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "13px 4px", borderBottom: "1px solid var(--ink-100)",
    }}>
      <span style={{ width: 132, flexShrink: 0, fontSize: 12.5, color: "var(--ink-500)" }}>{label}</span>
      <span style={{ minWidth: 0, fontSize: 13.5, fontWeight: 600, color: "var(--ink-800)" }}>{children}</span>
    </div>
  );
  const chip = {
    fontSize: 11.5, fontWeight: 700, color: "var(--primary-700)",
    background: "var(--primary-50)", borderRadius: 999, padding: "3px 9px",
  } as const;
  return (
    <MockShell label="Project memory">
      <div style={{ fontSize: 12.5, color: "var(--ink-500)", marginBottom: 4 }}>
        Everything the agent knows about your thesis so far.
      </div>
      <Row label="Research question">
        <span style={{
          display: "inline-block", maxWidth: "100%", whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis", verticalAlign: "bottom",
        }}>
          Does regulatory divergence…
        </span>
      </Row>
      <Row label="Gaps found">
        <span style={{ display: "inline-flex", gap: 6 }}>
          <span style={chip}>G1</span><span style={chip}>G2</span>
        </span>
      </Row>
      <Row label="Sources verified">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <span style={{ transition: "color .3s" }}>{12 + step}</span>
          <Badge tone="ok">CrossRef-checked</Badge>
        </span>
      </Row>
      <Row label="Current step">M2 · Literature review</Row>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 4px" }}>
        <span style={{ width: 132, flexShrink: 0, fontSize: 12.5, color: "var(--ink-500)" }}>Status</span>
        <Badge tone={done ? "ok" : "idle"}>{done ? "Done" : "In progress"}</Badge>
      </div>
    </MockShell>
  );
}


// CONCEPTUAL MODEL — the agent turns hypotheses into a path model and DRAWS it:
// the outcome sits ready, then each construct and its hypothesis path animates
// in, "building" the diagram before it loops.
function ModelMock() {
  const step = useCycle(4, 1000); // 0: outcome only, 1..3: reveal a predictor + its path
  const box = { w: 150, h: 44, x: 16 };
  const out = { w: 156, h: 54, x: 298, y: 93 };
  const outC = { x: out.x + out.w / 2, y: out.y + out.h / 2 };
  const constructs = [
    { label: "Attractiveness", h: "H1", y: 18 },
    { label: "Trustworthiness", h: "H2", y: 96 },
    { label: "Expertise", h: "H3", y: 174 },
  ];
  return (
    <MockShell label="Conceptual model · M3">
      <svg viewBox="0 0 470 232" style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label="Research model diagram">
        <defs>
          <marker id="lp-arw" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--primary-500)" />
          </marker>
        </defs>

        {/* hypothesis paths (behind the boxes) */}
        {constructs.map((c, i) => {
          const cy = c.y + box.h / 2;
          const x1 = box.x + box.w, x2 = out.x;
          const mx = (x1 + x2) / 2;
          const lx = mx - 4, ly = (cy + outC.y) / 2 - 8;
          return (
            <g key={c.h} style={{ opacity: i < step ? 1 : 0, transition: "opacity .45s" }}>
              <path d={`M${x1} ${cy} C ${mx} ${cy}, ${mx} ${outC.y}, ${x2 - 2} ${outC.y}`}
                fill="none" stroke="var(--primary-500)" strokeWidth="1.6" markerEnd="url(#lp-arw)" />
              <rect x={lx - 12} y={ly - 9} width="24" height="17" rx="5" fill="#fff" stroke="var(--primary-100)" />
              <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central"
                fontSize="10.5" fontWeight="700" fill="var(--primary-700)"
                style={{ fontFamily: "var(--font-sans)" }}>{c.h}</text>
            </g>
          );
        })}

        {/* predictor construct boxes */}
        {constructs.map((c, i) => (
          <g key={c.label} style={{ opacity: i < step ? 1 : 0, transition: "opacity .45s" }}>
            <rect x={box.x} y={c.y} width={box.w} height={box.h} rx="10" fill="#fff" stroke="var(--ink-200)" strokeWidth="1.2" />
            <text x={box.x + box.w / 2} y={c.y + box.h / 2} textAnchor="middle" dominantBaseline="central"
              fontSize="12.5" fontWeight="600" fill="var(--ink-800)"
              style={{ fontFamily: "var(--font-sans)" }}>{c.label}</text>
          </g>
        ))}

        {/* outcome (always present — the target the model builds toward) */}
        <rect x={out.x} y={out.y} width={out.w} height={out.h} rx="12"
          fill="var(--primary-50)" stroke="var(--primary-500)" strokeWidth="1.4" />
        <text x={outC.x} y={outC.y} textAnchor="middle" dominantBaseline="central"
          fontSize="13" fontWeight="700" fill="var(--primary-700)"
          style={{ fontFamily: "var(--font-sans)" }}>Purchase intention</text>
      </svg>
      <div style={{
        marginTop: 4, paddingTop: 14, borderTop: "1px dashed var(--ink-200)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <Badge tone={step >= 3 ? "ok" : "idle"}>{step >= 3 ? "Model ready" : "Building model…"}</Badge>
        <span style={{ fontSize: 12.5, color: "var(--ink-500)" }}>3 constructs · 3 hypotheses</span>
      </div>
    </MockShell>
  );
}


// AUTO THESIS — one prompt, full thesis: the typed topic sits at the top, then
// the five modules write themselves one after another (working → done), the
// "now writing" line following the active module, ending on a ready thesis.
function AutoThesisMock() {
  const modules = [
    { id: "M1", now: "M1 · Topic Discovery — framing the question",
      result: "Title & research question set" },
    { id: "M2", now: "M2 · Literature Review — verifying sources",
      result: "14 sources synthesised · gaps G1, G2" },
    { id: "M3", now: "M3 · Research Design — building the model",
      result: "3 constructs → purchase intention · H1–H3" },
    { id: "M4", now: "M4 · Analysis — reading the SmartPLS output",
      result: "H1 β .34 · H2 β .28 · H3 β .19 · all p<.05" },
    { id: "M5", now: "M5 · Writing — composing the chapters",
      result: "5 chapters drafted · every claim cited" },
  ];
  const step = useCycle(modules.length + 1, 1200); // done count 0..5; == len → finished
  const done = step >= modules.length;
  return (
    <MockShell label="Auto Thesis">
      {/* the one prompt */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "11px 13px",
        border: "1px solid var(--ink-200)", borderRadius: 12, background: "var(--ink-50)",
      }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--primary-600)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Prompt
        </span>
        <span style={{ fontSize: 13, color: "var(--ink-800)", fontWeight: 500 }}>
          KOL characteristics → purchase intent on TikTok Shop
        </span>
      </div>

      {/* status + the module currently being written */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "14px 0 12px" }}>
        <Badge tone={done ? "ok" : "idle"}>{done ? "Thesis ready" : "Auto Thesis running…"}</Badge>
        <span style={{ fontSize: 12.5, color: "var(--ink-500)", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {done ? "5 chapters · 14 references · APA 7" : modules[Math.min(step, modules.length - 1)].now}
        </span>
      </div>

      {/* M1→M5 progressing */}
      <div style={{ display: "flex", gap: 8 }}>
        {modules.map((m, i) => {
          const isDone = i < step;
          const active = i === step && !done;
          return (
            <div key={m.id} style={{
              flex: 1, textAlign: "center", padding: "9px 0", borderRadius: 10,
              fontSize: 12.5, fontWeight: 700,
              color: isDone ? "#fff" : active ? "var(--primary-700)" : "var(--ink-400)",
              background: isDone ? "var(--primary-600)" : active ? "var(--primary-50)" : "var(--ink-100)",
              boxShadow: active ? "0 0 0 1.5px var(--primary-500)" : "none",
              transition: "background .3s, color .3s, box-shadow .3s",
            }}>
              {m.id}{isDone ? " ✓" : ""}
            </div>
          );
        })}
      </div>

      {/* Result content: each finished module drops its output into the thesis,
          so the panel fills in as the run goes — you see what it produced, not
          just that it ran. Rows always occupy space (opacity toggles) so the
          panel height never jumps. */}
      <div style={{
        marginTop: 12, border: "1px solid var(--ink-200)", borderRadius: 12,
        background: "var(--ink-50)", padding: "10px 12px",
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        {modules.map((m, i) => {
          const shown = i < step;
          return (
            <div key={m.id} style={{
              display: "flex", alignItems: "center", gap: 9,
              opacity: shown ? 1 : 0.28,
              transform: shown ? "none" : "translateY(2px)",
              transition: "opacity .4s, transform .4s",
            }}>
              <span style={{
                width: 30, flexShrink: 0, textAlign: "center", fontSize: 10.5, fontWeight: 800,
                color: shown ? "#fff" : "var(--ink-400)",
                background: shown ? "var(--primary-600)" : "var(--ink-100)",
                borderRadius: 6, padding: "2px 0", transition: "background .3s, color .3s",
              }}>{m.id}</span>
              <span style={{
                fontSize: 12.5, color: shown ? "var(--ink-700)" : "var(--ink-400)",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>{shown ? m.result : "…"}</span>
              {shown && <span style={{ marginLeft: "auto", color: "var(--primary-600)", fontSize: 12 }}>✓</span>}
            </div>
          );
        })}
      </div>
    </MockShell>
  );
}


// CHAT — an auto-playing conversation that shows the agent DOING the work: it
// builds the conceptual model, then pulls verified citations, and loops. Not a
// text box waiting on input — the demo drives itself, like the others. Parked
// on the finished thread for reduced-motion users.
type Turn =
  | { role: "user"; text: ReactNode }
  | { role: "agent"; text: ReactNode; artifact?: "model" | "citations" };

const CHAT_SCRIPT: Turn[] = [
  { role: "user", text: "Build the conceptual model for my hypotheses." },
  {
    role: "agent",
    text: "Done — three predictors into one outcome, a hypothesis on each path:",
    artifact: "model",
  },
  { role: "user", text: "Now pull sources on the EU–US enforcement gap." },
  { role: "agent", text: "Found three, each CrossRef-checked:", artifact: "citations" },
];

/** The model the agent "draws" in the chat — compact, same SVG language as
    Fig. 2 so the product reads as one thing. */
function ChatModelCard() {
  const nodes = [
    { label: "Regime type", y: 6 },
    { label: "Enforcement", y: 47 },
    { label: "Redress", y: 88 },
  ];
  return (
    <div style={{ border: "1px solid var(--ink-200)", borderRadius: 10, background: "#fff", padding: "12px 12px 8px", marginTop: 8 }}>
      <svg viewBox="0 0 300 132" style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label="Generated conceptual model">
        <defs>
          <marker id="lp-chat-arw" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--primary-500)" />
          </marker>
        </defs>
        {nodes.map((n) => (
          <path key={n.label} d={`M120 ${n.y + 15} C 162 ${n.y + 15}, 170 66, 208 66`} fill="none" stroke="var(--primary-500)" strokeWidth={1.4} markerEnd="url(#lp-chat-arw)" />
        ))}
        {nodes.map((n) => (
          <g key={n.label}>
            <rect x={6} y={n.y} width={114} height={30} rx={7} fill="#fff" stroke="var(--ink-200)" strokeWidth={1.1} />
            <text x={63} y={n.y + 15} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600} fill="var(--ink-800)" style={{ fontFamily: "var(--font-sans)" }}>{n.label}</text>
          </g>
        ))}
        <rect x={208} y={46} width={86} height={40} rx={9} fill="var(--primary-50)" stroke="var(--primary-500)" strokeWidth={1.3} />
        <text x={251} y={66} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700} fill="var(--primary-700)" style={{ fontFamily: "var(--font-sans)" }}>Accountability</text>
      </svg>
      <div style={{ fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--ink-500)", marginTop: 4, textAlign: "center" }}>
        Conceptual model · 3 constructs · H1–H3
      </div>
    </div>
  );
}

/** The citations the agent "pulls" — real chips plus the verified badge. */
function ChatCitationsCard() {
  const cites = [
    { label: "Nguyen 2021", title: "Algorithmic accountability across jurisdictions", url: "https://doi.org/10.1016/j.chb.2021.106789" },
    { label: "Okafor 2023", title: "Toward measurable AI accountability", url: "https://doi.org/10.1145/3593013" },
    { label: "Schmidt 2022", title: "Regulatory divergence in AI governance" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
      {cites.map((c) => (
        <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--ink-600)", minWidth: 0 }}>
          <span style={{ color: "var(--moss-fg)", flexShrink: 0, display: "inline-flex" }}><IconCheck size={13} /></span>
          <CitationChip label={c.label} title={c.title} url={c.url} />
          <span style={{ color: "var(--ink-500)", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.title}</span>
        </div>
      ))}
      <div style={{ marginTop: 2 }}>
        <Badge tone="ok">14 sources · CrossRef-checked</Badge>
      </div>
    </div>
  );
}

function ChatMock() {
  const [shown, setShown] = useState(0);   // turns already in the thread
  const [typed, setTyped] = useState("");  // composer text for the pending user turn
  const [thinking, setThinking] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  // ONE state machine drives both the composer and the thread, so they stay in
  // sync: a user turn is TYPED into the composer, then "sent" (the bubble
  // appears and the composer clears); an agent turn shows the working dots then
  // replies; at the end it holds, then loops to an empty thread.
  useEffect(() => {
    if (typeof window !== "undefined"
        && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(CHAT_SCRIPT.length);
      return;
    }
    let t: ReturnType<typeof setTimeout>;
    if (shown >= CHAT_SCRIPT.length) {
      t = setTimeout(() => { setShown(0); setTyped(""); }, 1800);
      return () => clearTimeout(t);
    }
    const next = CHAT_SCRIPT[shown];
    if (next.role === "user") {
      const target = typeof next.text === "string" ? next.text : "";
      if (typed === target) {
        // fully typed → hit enter: reveal the bubble and clear the composer.
        t = setTimeout(() => { setShown(s => s + 1); setTyped(""); }, 180);
      } else {
        t = setTimeout(() => setTyped(target.slice(0, typed.length + 1)), 22);
      }
    } else {
      setThinking(true);
      t = setTimeout(() => { setThinking(false); setShown(s => s + 1); }, 650);
    }
    return () => clearTimeout(t);
  }, [shown, typed]);

  // The composer only "types" while the next turn to send is the user's; during
  // an agent reply (or when the thread is complete) it rests on the placeholder.
  const pendingUser = shown < CHAT_SCRIPT.length && CHAT_SCRIPT[shown].role === "user";

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [shown, thinking]);

  const AgentLabel = () => (
    <div style={{
      fontSize: 10.5, fontWeight: 700, letterSpacing: "0.04em",
      textTransform: "uppercase", color: "var(--primary-600)", marginBottom: 5,
    }}>
      Agent
    </div>
  );

  return (
    <MockShell label="Chat · thesis agent" pad={0}>
      <div
        ref={scroller}
        style={{
          minHeight: 316, maxHeight: 360, overflowY: "auto",
          padding: "18px 18px 8px", display: "flex", flexDirection: "column", gap: 14,
        }}
      >
        {CHAT_SCRIPT.slice(0, shown).map((turn, i) =>
          turn.role === "user" ? (
            <div key={i} style={{
              alignSelf: "flex-end", maxWidth: "84%",
              background: "var(--primary-600)", color: "#fff",
              borderRadius: "14px 14px 4px 14px", padding: "9px 13px",
              fontSize: 13.5, lineHeight: 1.5,
            }}>
              {turn.text}
            </div>
          ) : (
            <div key={i} style={{ alignSelf: "flex-start", width: turn.artifact ? "100%" : "auto", maxWidth: "94%" }}>
              <AgentLabel />
              <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--ink-700)" }}>{turn.text}</div>
              {turn.artifact === "model" && <ChatModelCard />}
              {turn.artifact === "citations" && <ChatCitationsCard />}
            </div>
          ),
        )}
        {thinking && (
          <div style={{ alignSelf: "flex-start" }}>
            <AgentLabel />
            <div style={{ display: "inline-flex", gap: 4, padding: "2px 0" }} aria-label="Agent is working">
              {[0, 1, 2].map(i => (
                <span key={i} className="lp-demo-pulse" style={{ width: 6, height: 6, borderRadius: 999, background: "var(--ink-300)" }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* faux composer — the chat affordance; the demo drives itself */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "12px 14px 14px", borderTop: "1px solid var(--ink-100)" }}>
        <div style={{
          flex: 1, fontFamily: "var(--font-sans)", fontSize: 13.5,
          color: pendingUser && typed ? "var(--ink-800)" : "var(--ink-400)",
          border: "1px solid var(--ink-200)", borderRadius: 10, padding: "10px 12px",
          background: "#fff", whiteSpace: "nowrap", overflow: "hidden",
        }}>
          {pendingUser ? (
            <>{typed}<span className="lp-caret" /></>
          ) : (
            "Ask it to build, research, or rewrite…"
          )}
        </div>
        <span style={{
          flexShrink: 0, width: 38, height: 38, borderRadius: 10,
          background: "var(--primary-600)", color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
        }} aria-hidden>
          <IconArrow size={17} />
        </span>
      </div>
    </MockShell>
  );
}


type Feature = { eyebrow: string; title: string; body: string; demo: ReactNode };

const FEATURES: Feature[] = [
  {
    eyebrow: "Auto Thesis",
    title: "From one prompt to a full thesis.",
    body: "Type your topic once and Auto Thesis writes the whole thing end-to-end — topic, literature, design, analysis and chapters — module by module, while you watch. Stop and steer any time.",
    demo: <AutoThesisMock />,
  },
  {
    eyebrow: "Chat",
    title: "Or just talk to your agent.",
    body: "You're never locked out of the loop. Ask a question, challenge a source, or say what to change — the agent answers grounded in your library, cites what it claims, then edits the draft in place.",
    demo: <ChatMock />,
  },
  {
    eyebrow: "Traceable citations",
    title: "Claims that link to the exact source.",
    body: "Every sentence the agent writes ties back to a real paper you can open — each citation CrossRef-checked, never invented. Open the reference and land on the exact claim.",
    demo: <CitationsMock />,
  },
  {
    eyebrow: "Source-grounded writing",
    title: "Writes from your papers, not the web.",
    body: "It draws only on the PDFs you upload, reading your library one source at a time, so your literature review reflects your judgement — not a model's training data.",
    demo: <SourcesMock />,
  },
  {
    eyebrow: "Context store",
    title: "A live memory you can inspect.",
    body: "Everything the agent learns — your question, the gaps, the verified sources, where you are — is committed to a store you can open any time. Nothing is hidden in a black box.",
    demo: <ContextMock />,
  },
  {
    eyebrow: "Conceptual model · M3",
    title: "Generate your research model, visualized.",
    body: "The agent turns your hypotheses into a conceptual model — the constructs and the paths between them — and draws it as a diagram you can see and refine before you ever run the analysis.",
    demo: <ModelMock />,
  },
];


function FeatureRow({ eyebrow, title, body, demo, reverse }: Feature & { reverse: boolean }) {
  return (
    <Reveal>
      <div className={`lp-feat-row${reverse ? " reverse" : ""}`}>
        <div className="lp-feat-text">
          <div className="lp-eyebrow" style={{ color: "var(--primary-600)", marginBottom: 14 }}>
            {eyebrow}
          </div>
          <h3 style={{
            fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: 26,
            letterSpacing: "-0.02em", lineHeight: 1.15, color: "var(--ink-900)", margin: 0,
          }}>
            {title}
          </h3>
          <p className="lp-lead" style={{ fontSize: 16, marginTop: 14, maxWidth: 460 }}>
            {body}
          </p>
        </div>
        <div className="lp-feat-demo">{demo}</div>
      </div>
    </Reveal>
  );
}


export function Features() {
  return (
    <section id="features" className="lp-sec">
      <div className="lp-wrap">
        <SectionHead
          eyebrow="Core features"
          title="Built for serious thesis writing."
          sub="Not a chatbot with citations bolted on — a workspace where the agent, your sources, and your argument work together."
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 96, marginTop: 72 }}>
          {FEATURES.map((f, i) => (
            <FeatureRow key={f.eyebrow} {...f} reverse={i % 2 === 1} />
          ))}
        </div>
      </div>
    </section>
  );
}
