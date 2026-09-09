/**
 * The idea→thesis product demo: one research question written out as a real
 * document, module by module.
 *
 * Lifted out of Hero.tsx, which had grown to ~970 lines with 780 of them being
 * this one drawing. It moved because the auth screens show it too (see
 * app/components/auth/AuthExplainer.tsx) and a second copy would have drifted
 * from this one the first time the document changed.
 *
 * Everything here reads `--ink-*`, `--primary-*`, `--moss-*` and the `.lp-*`
 * classes from landing.css. Those tokens are scoped to `.lp-root`, so any
 * surface rendering this component has to import landing.css and put a
 * `.lp-root` ancestor above it. The landing page gets both from its own page
 * shell; the auth panel does it explicitly.
 */
"use client";

import { useEffect, useRef, useState } from "react";

import { Badge, CitationChip } from "./ds";
import { IconCheck } from "./shared";

// -- hero demo: one idea → generated step by step → a full thesis document --
const DEMO_MODULES = ["M1", "M2", "M3", "M4", "M5"];
const DEMO_CAPTIONS = [
  "Reading your idea…",
  "M1 · Topic Discovery — framing the research question",
  "M2 · Literature Review — synthesising 14 sources",
  "M3 · Research Design — choosing the methodology",
  "M4 · Data Analysis — reading the results",
  // Not "page-cited": verify_page_numbers returns "unverified" whenever there
  // is no source PDF, and its own docstring defers the page lookup to a
  // follow-on project. Citations are traced to the source, not to the page.
  "M5 · Writing — draft complete, every claim traced to a source",
];

const FIGURE_BARS: Array<[string, number]> = [
  ["EU", 82],
  ["UK", 54],
  ["US-fed", 38],
  ["US-CA", 66],
  ["SG", 30],
  ["AU", 46],
];

const REFERENCES = [
  "Young, M., Katell, M., & Krafft, P. M. (2019). Municipal surveillance regulation and algorithmic accountability. Big Data & Society, 6(2).",
  "Hunt, R., & McKelvey, F. (2019). Algorithmic regulation in media and cultural policy. Journal of Information Policy, 9.",
  "de Menezes Acioly, B., et al. (2024). Accountability in Brazilian artificial intelligence regulation. Journal of AI Law and Regulation, 1(1).",
];

// Table 1: the thesis's central comparison. Dimension, then the two regimes.
const COMPARISON_ROWS: Array<[string, string, string]> = [
  ["Legal basis", "AI Act (2024), horizontal", "Sectoral — FTC Act, state laws"],
  ["Enforcement", "Ex-ante conformity checks", "Ex-post, complaint-driven"],
  ["Scope", "Risk-tiered, cross-sector", "Domain-specific"],
  ["Individual redress", "Right to explanation", "Limited private right of action"],
  ["Transparency", "Mandatory disclosure", "Voluntary / sector guidance"],
];

/** The last step, where the whole document is on screen at once. */
const DONE_STEP = 5;

/** Table 1 — EU vs US accountability mechanisms, the EU column tinted as the
    thesis's focal case. */
function ComparisonTable() {
  const cell = {
    padding: "7px 10px",
    borderBottom: "1px solid var(--ink-100)",
    verticalAlign: "top" as const,
  };
  return (
    <div className="lp-fin" style={{ marginTop: 4 }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--font-sans)",
          fontSize: 12.5,
          lineHeight: 1.4,
        }}
      >
        <thead>
          <tr>
            {["Dimension", "European Union", "United States"].map((h, i) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  fontWeight: 700,
                  color: "var(--ink-700)",
                  padding: "8px 10px",
                  borderBottom: "2px solid var(--ink-300)",
                  background: i === 1 ? "var(--primary-50)" : "transparent",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARISON_ROWS.map(([dim, eu, us]) => (
            <tr key={dim}>
              <td style={{ ...cell, fontWeight: 600, color: "var(--ink-700)" }}>
                {dim}
              </td>
              <td style={{ ...cell, color: "var(--ink-700)", background: "var(--primary-50)" }}>
                {eu}
              </td>
              <td style={{ ...cell, color: "var(--ink-600)" }}>{us}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: 11.5,
          color: "var(--ink-500)",
          marginTop: 10,
          textAlign: "center",
        }}
      >
        Table 1 · Accountability mechanisms compared across regimes
      </div>
    </div>
  );
}

/** Fig. 2 — a research conceptual model: three predictor constructs feeding a
    single outcome, each path carrying a hypothesis. Same SVG language as the
    Features ModelMock so the two read as one product. */
function ModelFigure() {
  const box = { w: 154, h: 46, x: 14 };
  const out = { w: 150, h: 58, x: 322, y: 91 };
  const outC = { x: out.x + out.w / 2, y: out.y + out.h / 2 };
  const constructs = [
    { label: "Regime type", h: "H1", y: 20 },
    { label: "Enforcement timing", h: "H2", y: 97 },
    { label: "Redress strength", h: "H3", y: 174 },
  ];
  return (
    <figure
      className="lp-fin"
      style={{
        margin: "18px 0 0",
        border: "1px solid var(--ink-200)",
        borderRadius: 12,
        padding: "20px 22px",
      }}
    >
      <svg
        viewBox="0 0 496 240"
        style={{ width: "100%", height: "auto", display: "block" }}
        role="img"
        aria-label="Conceptual model: predictors of accountability outcomes"
      >
        <defs>
          <marker id="lp-arw2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--primary-500)" />
          </marker>
        </defs>

        {/* hypothesis paths (behind the boxes) */}
        {constructs.map((c) => {
          const cy = c.y + box.h / 2;
          const x1 = box.x + box.w;
          const x2 = out.x;
          const mx = (x1 + x2) / 2;
          const ly = (cy + outC.y) / 2 - 7;
          return (
            <g key={c.h}>
              <path
                d={`M${x1} ${cy} C ${mx} ${cy}, ${mx} ${outC.y}, ${x2 - 2} ${outC.y}`}
                fill="none"
                stroke="var(--primary-500)"
                strokeWidth={1.6}
                markerEnd="url(#lp-arw2)"
              />
              <rect x={mx - 13} y={ly - 9} width={26} height={18} rx={6} fill="#fff" stroke="var(--primary-100)" />
              <text x={mx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize={10.5} fontWeight={700} fill="var(--primary-700)" style={{ fontFamily: "var(--font-sans)" }}>
                {c.h}
              </text>
            </g>
          );
        })}

        {/* predictor constructs */}
        {constructs.map((c) => (
          <g key={c.label}>
            <rect x={box.x} y={c.y} width={box.w} height={box.h} rx={10} fill="#fff" stroke="var(--ink-200)" strokeWidth={1.2} />
            <text x={box.x + box.w / 2} y={c.y + box.h / 2} textAnchor="middle" dominantBaseline="central" fontSize={12.5} fontWeight={600} fill="var(--ink-800)" style={{ fontFamily: "var(--font-sans)" }}>
              {c.label}
            </text>
          </g>
        ))}

        {/* outcome */}
        <rect x={out.x} y={out.y} width={out.w} height={out.h} rx={12} fill="var(--primary-50)" stroke="var(--primary-500)" strokeWidth={1.4} />
        <text x={outC.x} y={outC.y} textAnchor="middle" dominantBaseline="central" fontSize={13} fontWeight={700} fill="var(--primary-700)" style={{ fontFamily: "var(--font-sans)" }}>
          Accountability
        </text>
      </svg>
      <figcaption
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: 11.5,
          color: "var(--ink-500)",
          marginTop: 12,
          textAlign: "center",
        }}
      >
        Fig. 2 · Predictors of accountability outcomes (H1–H3)
      </figcaption>
    </figure>
  );
}

/** The finished thesis, rendered as a real serif document on paper. */
function ThesisDocument({ step }: { step: number }) {
  return (
    <div
      className="lp-thesis-doc"
      style={{ fontFamily: "var(--font-serif)", color: "var(--ink-800)" }}
    >
      {/* title block */}
      <div
        className="lp-fin"
        style={{
          textAlign: "center",
          paddingBottom: 22,
          borderBottom: "1px solid var(--ink-200)",
        }}
      >
        <div
          className="lp-eyebrow"
          style={{
            fontFamily: "var(--font-sans)",
            color: "var(--primary-600)",
            marginBottom: 14,
          }}
        >
          Master&apos;s Thesis · Draft
        </div>
        <h3
          style={{
            fontSize: "clamp(20px,2.4vw,27px)",
            fontWeight: 800,
            letterSpacing: "-0.015em",
            lineHeight: 1.18,
            maxWidth: 540,
            margin: "0 auto",
          }}
        >
          Regulating Algorithmic Accountability: EU and US Frameworks Compared
        </h3>
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: 12.5,
            color: "var(--ink-400)",
            marginTop: 16,
            letterSpacing: "0.02em",
          }}
        >
          Nguyen Minh Anh · Faculty of Law · 2026
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 8,
            marginTop: 16,
            flexWrap: "wrap",
          }}
        >
          {/* Not "100% citations verified": a source is accepted on a DOI *or* a
              URL, and the DOI existence check is off by default, so "verified"
              overstates it. Every citation IS traced to the reference list. */}
          <Badge tone="ok">Every citation traced</Badge>
          <span
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: 11.5,
              fontWeight: 600,
              color: "var(--ink-500)",
              background: "var(--ink-100)",
              borderRadius: 999,
              padding: "5px 11px",
            }}
          >
            14 references · APA 7
          </span>
        </div>
      </div>

      {/* abstract */}
      {step >= 2 && (
        <div className="lp-fin" style={{ marginTop: 24 }}>
          <h4 className="lp-doc-h">Abstract</h4>
          <p style={{ fontSize: 14.5, lineHeight: 1.75 }}>
            This thesis compares how algorithmic accountability is enforced
            across European and United States regulatory regimes, drawing on
            fourteen peer-reviewed sources and a comparative case analysis of
            six jurisdictions.
          </p>
        </div>
      )}

      {/* introduction */}
      {step >= 3 && (
        <div className="lp-fin" style={{ marginTop: 22 }}>
          <h4 className="lp-doc-h">1 · Introduction</h4>
          <p style={{ fontSize: 14.5, lineHeight: 1.75 }}>
            Automated decision systems now mediate access to credit, employment,
            and public services, yet the mechanisms that hold their operators to
            account remain unevenly distributed. The enforcement asymmetry
            between EU and US regulators is well documented{" "}
            <CitationChip
              label="Young 2019"
              title="Municipal surveillance regulation and algorithmic accountability"
              url="https://doi.org/10.1177/2053951719868492"
            />
            .
          </p>
          <p
            style={{ fontSize: 14.5, lineHeight: 1.75, textIndent: "1.4em" }}
          >
            This divergence raises a measurement problem: without a shared
            accountability metric, cross-border comparison rests on incompatible
            baselines{" "}
            <CitationChip
              label="Hunt 2019"
              title="Algorithmic regulation in media and cultural policy"
              url="https://doi.org/10.5325/jinfopoli.9.2019.0307"
            />
            .
          </p>
        </div>
      )}

      {/* comparative framework — a real table + a real chart */}
      {step >= 4 && (
        <div className="lp-fin" style={{ marginTop: 22 }}>
          <h4 className="lp-doc-h">2 · Comparative Framework</h4>
          <p style={{ fontSize: 14.5, lineHeight: 1.75, marginBottom: 14 }}>
            The two regimes diverge less in ambition than in instrument. Table 1
            sets their accountability mechanisms side by side; Fig. 1 shows how
            unevenly each has been enforced.
          </p>
          <ComparisonTable />
          <figure
            style={{
              margin: "18px 0 0",
              border: "1px solid var(--ink-200)",
              borderRadius: 12,
              padding: "18px 20px",
            }}
          >
            {/* Definite heights: the bars used `height: X%` against a parent
                with no definite height, which resolves to 0 — the chart looked
                empty. Map each value to pixels instead. */}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 12, height: 100, borderBottom: "1px solid var(--ink-200)" }}>
              {FIGURE_BARS.map(([label, value]) => (
                <div
                  key={label}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    gap: 5,
                    flex: 1,
                    height: "100%",
                  }}
                >
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-400)" }}>
                    {value}
                  </span>
                  <span
                    style={{
                      width: "100%",
                      maxWidth: 28,
                      height: Math.round((value / 82) * 74),
                      borderRadius: "3px 3px 0 0",
                      background: label === "EU" ? "var(--primary-600)" : "var(--primary-500)",
                      opacity: label === "EU" ? 1 : 0.5,
                    }}
                  />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 5 }}>
              {FIGURE_BARS.map(([label]) => (
                <span key={label} style={{ flex: 1, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 9.5, color: "var(--ink-500)" }}>
                  {label}
                </span>
              ))}
            </div>
            <figcaption
              style={{
                fontFamily: "var(--font-sans)",
                fontSize: 11.5,
                color: "var(--ink-500)",
                marginTop: 12,
                textAlign: "center",
              }}
            >
              Fig. 1 · Enforcement actions by jurisdiction, 2019–2024
            </figcaption>
          </figure>
        </div>
      )}

      {/* conceptual model + references */}
      {step >= 5 && (
        <div className="lp-fin" style={{ marginTop: 22 }}>
          <h4 className="lp-doc-h">3 · Conceptual Model</h4>
          <p style={{ fontSize: 14.5, lineHeight: 1.75, marginBottom: 6 }}>
            Synthesising the comparison, enforcement outcomes are modelled as a
            function of regime design rather than statutory ambition (Fig. 2).
          </p>
          <ModelFigure />
          <h4 className="lp-doc-h" style={{ marginTop: 24 }}>References</h4>
          <div
            style={{ display: "flex", flexDirection: "column", gap: 10 }}
          >
            {REFERENCES.map((ref) => (
              <div
                key={ref}
                style={{
                  display: "flex",
                  gap: 10,
                  fontSize: 12.5,
                  lineHeight: 1.55,
                  color: "var(--ink-600)",
                }}
              >
                <span style={{ color: "var(--moss-fg)", flexShrink: 0 }}>
                  <IconCheck size={13} />
                </span>
                <span style={{ textIndent: "-1.2em", paddingLeft: "1.2em" }}>
                  {ref}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Reports whether the reader has asked for reduced motion, or `null` while
 * that is still unknown (the server render and the first client paint, where
 * matchMedia does not exist yet).
 *
 * The `null` matters: defaulting to "motion is fine" and correcting in an
 * effect would start the write-out sequence and then yank it back, which is
 * the exact flash of movement the preference exists to prevent.
 */
function usePrefersReducedMotion(): boolean | null {
  const [reduced, setReduced] = useState<boolean | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  return reduced;
}

type ProductMockProps = {
  /** Height of the frame once the draft is finished and zoomed to fit. */
  doneHeight?: number;
  /** Height of the frame while the modules are still writing. */
  writingHeight?: number;
};

/**
 * The looping demo. Defaults are the landing hero's dimensions; the auth
 * explainer passes smaller ones because its column is shorter than a hero.
 */
export function ProductMock({
  doneHeight = 600,
  writingHeight = 420,
}: ProductMockProps = {}) {
  // One timer per step keeps the sequence readable: 1.15s per module, then a
  // 6.5s hold on the finished draft before it loops.
  const [step, setStep] = useState(0);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    // Unknown preference: hold on the idea card rather than guess.
    if (reduced === null) return;
    // Reduced motion gets the outcome without the choreography — the finished
    // thesis, held there, no timer. landing.css already flattens the CSS
    // keyframes under the same query; this is the JS half of that.
    if (reduced) {
      setStep(DONE_STEP);
      return;
    }
    const id = setTimeout(
      () => setStep((s) => (s >= DONE_STEP ? 0 : s + 1)),
      step >= DONE_STEP ? 6500 : 1150,
    );
    return () => clearTimeout(id);
  }, [step, reduced]);

  const done = step >= DONE_STEP;

  // Zoom the finished page to fit the viewport EXACTLY, measured rather than
  // guessed: the document grew (table, chart, conceptual model) past any fixed
  // scale, and Fig. 2 at the very bottom was falling below the clip. Measuring
  // offsetHeight (unaffected by the transform) keeps the whole thesis in frame
  // however much content it ends up with.
  const docRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(0.42);
  useEffect(() => {
    function measure() {
      if (!done) return;
      const h = docRef.current?.offsetHeight ?? 0;
      if (h > 0) setFit(Math.min(0.58, (doneHeight - 56) / h));
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [done, doneHeight]);

  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid var(--ink-200)",
        borderRadius: 20,
        boxShadow: "var(--shadow-pop)",
        overflow: "hidden",
        textAlign: "left",
      }}
    >
      {/* chrome */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          borderBottom: "1px solid var(--ink-100)",
          background: "var(--ink-50)",
        }}
      >
        <div style={{ display: "flex", gap: 6 }}>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              style={{
                width: 10,
                height: 10,
                borderRadius: 999,
                background: "#e4e4e7",
              }}
            />
          ))}
        </div>
        <span
          className="lp-serif"
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "var(--ink-700)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          Regulating Algorithmic Accountability
        </span>
        <span
          style={{
            marginLeft: "auto",
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <Badge tone={done ? "ok" : "run"} pulse={!done}>
            {done
              ? "Draft ready"
              : `${DEMO_MODULES[Math.min(step, 4)]} · working`}
          </Badge>
          {done && (
            <span
              className="lp-fin"
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--primary-600)",
                background: "var(--primary-50)",
                borderRadius: 999,
                padding: "5px 12px",
                whiteSpace: "nowrap",
              }}
            >
              ⤓ Export .docx
            </span>
          )}
        </span>
      </div>

      {/* module tick strip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "11px 18px",
          borderBottom: "1px solid var(--ink-100)",
        }}
      >
        <span
          className="lp-eyebrow lp-modstrip-label"
          style={{ color: "var(--ink-400)", flexShrink: 0 }}
        >
          Idea → thesis
        </span>
        <div className="lp-modstrip" style={{ display: "flex", gap: 6, flex: 1 }}>
          {DEMO_MODULES.map((id, i) => {
            const isDone = step >= i + 1;
            const active = step === i && !done;
            return (
              <div
                key={id}
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 8px",
                  borderRadius: 999,
                  background: isDone
                    ? "var(--moss-bg)"
                    : active
                      ? "var(--primary-50)"
                      : "var(--ink-50)",
                  border: `1px solid ${
                    isDone
                      ? "transparent"
                      : active
                        ? "var(--primary-100)"
                        : "var(--ink-100)"
                  }`,
                  transition: "background .2s",
                }}
              >
                <span
                  className={active ? "lp-demo-pulse" : ""}
                  style={{
                    width: 13,
                    height: 13,
                    borderRadius: 999,
                    flexShrink: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 8,
                    fontWeight: 800,
                    background: isDone
                      ? "var(--moss-fg)"
                      : active
                        ? "var(--primary-600)"
                        : "var(--ink-200)",
                    color: "#fff",
                  }}
                >
                  {isDone ? "✓" : ""}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 10.5,
                    fontWeight: 700,
                    color: isDone
                      ? "var(--moss-fg)"
                      : active
                        ? "var(--primary-600)"
                        : "var(--ink-400)",
                  }}
                >
                  {id}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* the thesis document (the result) */}
      <div style={{ position: "relative" }}>
        <div
          style={{
            padding: "28px 34px",
            height: done ? doneHeight : writingHeight,
            overflow: "hidden",
            // Fade the bottom WHILE writing (content runs off-screen, hinting
            // more). At done we zoom out to the whole page, so no fade.
            WebkitMaskImage: done
              ? "none"
              : "linear-gradient(to bottom, #000 86%, transparent)",
            maskImage: done
              ? "none"
              : "linear-gradient(to bottom, #000 86%, transparent)",
          }}
        >
          {step === 0 ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                gap: 16,
                textAlign: "center",
              }}
            >
              <div
                style={{
                  border: "1px dashed var(--ink-300)",
                  borderRadius: 12,
                  padding: "16px 20px",
                  maxWidth: 420,
                  background: "var(--ink-50)",
                }}
              >
                <div
                  className="lp-eyebrow"
                  style={{ color: "var(--ink-400)", marginBottom: 8 }}
                >
                  Your idea
                </div>
                <div
                  className="lp-serif"
                  style={{
                    fontSize: 16,
                    color: "var(--ink-700)",
                    lineHeight: 1.5,
                  }}
                >
                  “How does algorithmic accountability differ between EU and US
                  regulators?”
                </div>
              </div>
              <div
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: 12.5,
                  color: "var(--ink-400)",
                }}
              >
                Reading your idea…
              </div>
            </div>
          ) : (
            // Follow-scroll: each module writes a new section BELOW the last, so
            // the view pans down to keep the freshly-written part visible —
            // otherwise everything after the abstract stayed clipped off-screen.
            // Offsets (px) roughly track cumulative section height per step.
            <div
              ref={docRef}
              style={{
                maxWidth: 620,
                margin: "0 auto",
                // While writing (M1–M4): follow-scroll down to the newest
                // section. At M5/done: zoom OUT to the measured fit so the whole
                // finished thesis — title through the conceptual model and
                // references — is visible at once, never clipped.
                transformOrigin: "top center",
                transform: done
                  ? `scale(${fit})`
                  : `translateY(-${[0, 0, 0, 60, 400][step] ?? 0}px)`,
                transition: "transform 1.1s ease",
              }}
            >
              <ThesisDocument step={step} />
            </div>
          )}
        </div>
      </div>

      {/* caption + progress */}
      <div
        style={{
          padding: "11px 18px",
          borderTop: "1px solid var(--ink-100)",
          display: "flex",
          alignItems: "center",
          gap: 14,
        }}
      >
        {/* Names the mode explicitly — this is Auto Thesis writing the whole
            document from the one idea above. */}
        <span
          className="lp-eyebrow"
          style={{
            color: done ? "var(--primary-600)" : "var(--ink-400)",
            fontSize: 10,
            flexShrink: 0,
          }}
        >
          {done ? "Auto Thesis · done" : "Auto Thesis"}
        </span>
        <span style={{ width: 1, height: 12, background: "var(--ink-200)", flexShrink: 0 }} aria-hidden />
        <span style={{ fontSize: 12, color: "var(--ink-500)", flex: 1 }}>
          {DEMO_CAPTIONS[step]}
        </span>
        {/* No Replay under reduced motion: the sequence it would restart is the
            thing that preference switched off, and the effect above would drag
            it straight back to the finished draft anyway. */}
        {!reduced && (
          <button
            type="button"
            onClick={() => setStep(0)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--ink-500)",
            }}
          >
            ▶ Replay
          </button>
        )}
      </div>
      <div style={{ height: 3, background: "var(--ink-100)" }}>
        <div
          style={{
            height: "100%",
            width: `${(step / DONE_STEP) * 100}%`,
            background: "var(--primary-600)",
            transition: "width .5s ease",
          }}
        />
      </div>
    </div>
  );
}
