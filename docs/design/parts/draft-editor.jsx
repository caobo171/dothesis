// Draft editor — read/edit the thesis with margin citations.

const DraftEditor = ({ go, citationStyle = "APA" }) => {
  const [activeCite, setActiveCite] = useState(null);

  // citation render helpers
  const formatInline = (key, year, authors) => {
    const lastName = authors.split(",")[0];
    const etAl = authors.split(",").length > 2 ? " et al." : "";
    switch (citationStyle) {
      case "MLA": return `(${lastName}${etAl})`;
      case "Chicago": return `(${lastName}${etAl} ${year})`;
      case "IEEE":  return `[${key}]`;
      case "Harvard": return `(${lastName}${etAl}, ${year})`;
      default: return `(${lastName}${etAl}, ${year})`;
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr 320px", minHeight: "calc(100vh - 320px)" }}>
      {/* Outline rail */}
      <OutlineRail />

      {/* Document */}
      <div style={{ padding: "48px 56px", borderRight: "1px solid var(--ink-100)", background: "var(--paper)" }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <div className="eyebrow" style={{ color: "var(--blue-600)" }}>Master's thesis · Draft</div>
          <h1 style={{
            fontFamily: "var(--font-serif)",
            fontSize: 32,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            lineHeight: 1.15,
            marginTop: 10,
          }}>
            Algorithmic Decision-Making and Democratic Accountability
          </h1>
          <div style={{
            fontFamily: "var(--font-serif)",
            fontSize: 18,
            fontStyle: "italic",
            color: "var(--ink-500)",
            marginTop: 6,
          }}>
            A Comparative Study of EU and US Regulatory Frameworks
          </div>
          <div style={{
            marginTop: 16,
            fontSize: 13,
            color: "var(--ink-400)",
            display: "flex",
            gap: 18,
            fontWeight: 600,
            flexWrap: "wrap",
          }}>
            <span>jeendeet</span>
            <span>·</span>
            <span>14,820 / 27,000 words</span>
            <span>·</span>
            <span>32 verified citations</span>
            <span>·</span>
            <span>Last sync 12s ago</span>
          </div>

          <hr style={{
            border: "none", borderTop: "1px solid var(--ink-100)", margin: "28px 0",
          }} />

              <h2 style={H2}>Abstract</h2>
              <p style={{ ...P, fontStyle: "italic", color: "var(--ink-700)" }}>
                This thesis offers a comparative legal analysis of the European Union's risk-based AI Act and
                the United States' sectoral regulatory architecture, with particular attention to enforcement
                mechanisms for algorithmic decisions taken by public administrations. Drawing on 32 verified
                sources spanning administrative law, computer science, and political theory, the study argues
                that procedural accountability — rather than substantive prohibition — better predicts citizen trust
                in algorithmic governance regimes.
              </p>

              <h2 style={H2}>1. Introduction</h2>
              <p style={P}>
                Public administrations increasingly delegate consequential decisions — from asylum triage to
                welfare-fraud detection — to algorithmic systems
                <Cite ck="Engstrom2020" inline={formatInline("Engstrom2020", 2020, "Engstrom, D. F., Ho, D. E., Sharkey, C. M.")} setActive={setActiveCite} />.
                This delegation produces a tension that lies at the heart of contemporary democratic theory:
                how can citizens hold to account decisions that they cannot fully see, understand, or contest?
                The European Union has answered this question with a horizontal, risk-tiered statute
                <Cite ck="Veale2021" inline={formatInline("Veale2021", 2021, "Veale, M., & Borgesius, F. Z.")} setActive={setActiveCite} />,
                while the United States has, to date, layered narrower sectoral controls over a NIST-led
                voluntary framework
                <Cite ck="Engstrom2020" inline={formatInline("Engstrom2020", 2020, "Engstrom, D. F., Ho, D. E., Sharkey, C. M.")} setActive={setActiveCite} />.
              </p>
              <p style={P}>
                The contrast is more than stylistic. Where the EU AI Act criminalises certain uses — social
                scoring by public authorities, real-time biometric identification in public spaces — the US
                approach instead asks federal agencies to articulate sector-specific risk thresholds
                <Cite ck="Hacker2024" inline={formatInline("Hacker2024", 2024, "Hacker, P., Engel, A., & Mauer, M.")} setActive={setActiveCite} />.
                The result is two regimes that nominally pursue the same goal — trustworthy AI — but locate
                accountability at very different points in the policy stack.
              </p>

              <ResearchNote>
                <b>Crafter · Discussion</b> · Drafted 14s ago. Coherence score 92 / 100. Two minor hedging
                opportunities flagged by Narrator — accept all to apply.
              </ResearchNote>

              <h2 style={H2}>4. Comparative Analysis</h2>
              <h3 style={H3}>4.1 The EU AI Act: Risk-Based Classification</h3>
              <p style={P}>
                Article 6 of the AI Act establishes a four-tier classification — unacceptable, high, limited, and
                minimal risk — that determines the regulatory obligations attached to each system
                <Cite ck="Veale2021" inline={formatInline("Veale2021", 2021, "Veale, M., & Borgesius, F. Z.")} setActive={setActiveCite} />.
                The high-risk tier, which subsumes most public-sector deployments of consequence, requires
                conformity assessments, post-market monitoring, and the maintenance of detailed technical
                documentation. As Smuha
                <Cite ck="Smuha2021" inline={formatInline("Smuha2021", 2021, "Smuha, N. A.")} setActive={setActiveCite} />
                observes, this represents a deliberate translation of product-safety logic into the digital
                policy domain.
              </p>

              <div style={{
                background: "var(--blue-50)",
                border: "1px solid var(--blue-100)",
                borderRadius: 14,
                padding: 18,
                margin: "20px 0",
                display: "flex",
                gap: 12,
                alignItems: "flex-start",
              }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 10,
                  background: "var(--blue-600)", color: "white",
                  display: "grid", placeItems: "center", flexShrink: 0,
                }}>
                  <Icon name="spark" size={16} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: "var(--blue-600)", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    Crafter · Results is writing here
                  </div>
                  <div style={{ fontSize: 14, color: "var(--ink-800)", marginTop: 6, lineHeight: 1.5 }}>
                    Drafting §4.2 — <i>US sectoral approach: NIST + state frameworks.</i> Citations being
                    queued: Engstrom et al. 2020, NIST AI RMF 1.0, Calo 2017…
                  </div>
                  <div style={{
                    marginTop: 10, display: "flex", gap: 4, alignItems: "center",
                  }}>
                    <CursorBlock /> <span style={{ fontSize: 12, color: "var(--ink-500)" }}>writing now</span>
                  </div>
                </div>
              </div>

              <h3 style={H3}>4.2 The US Sectoral Approach: NIST + State Frameworks</h3>
              <p style={P}>
                In contrast, the US has pursued what Hacker, Engel and Mauer
                <Cite ck="Hacker2024" inline={formatInline("Hacker2024", 2024, "Hacker, P., Engel, A., & Mauer, M.")} setActive={setActiveCite} />
                describe as a "polycentric" governance pattern — federal sectoral agencies (the EEOC, FTC,
                HUD, and so on) issue domain-specific guidance, the NIST AI Risk Management Framework
                provides a horizontal vocabulary, and individual states fill gaps with their own
                accountability statutes. Of particular interest is Colorado's SB 24-205…
              </p>
            </div>
          </div>

          {/* Right rail: citations */}
          <CitationRail activeCite={activeCite} formatInline={formatInline} />
        </div>
  );
};

const H2 = {
  fontFamily: "var(--font-serif)",
  fontSize: 26,
  fontWeight: 600,
  letterSpacing: "-0.01em",
  marginTop: 40,
  marginBottom: 12,
  color: "var(--ink-900)",
};
const H3 = {
  fontFamily: "var(--font-serif)",
  fontSize: 19,
  fontWeight: 600,
  letterSpacing: "-0.01em",
  marginTop: 28,
  marginBottom: 8,
  color: "var(--ink-900)",
};
const P = {
  fontFamily: "var(--font-serif)",
  fontSize: 16.5,
  lineHeight: 1.65,
  color: "var(--ink-800)",
  margin: "0 0 16px",
  textWrap: "pretty",
};

const Cite = ({ ck, inline, setActive }) => (
  <sup
    onClick={() => setActive(ck)}
    style={{
      color: "var(--blue-600)",
      cursor: "pointer",
      fontSize: 14,
      fontFamily: "var(--font-sans)",
      fontWeight: 600,
      padding: "0 1px",
      verticalAlign: "baseline",
    }}
  >{inline}</sup>
);

const CursorBlock = () => (
  <span style={{
    display: "inline-block", width: 8, height: 16, background: "var(--blue-600)",
    animation: "blink 0.9s steps(2, start) infinite",
  }}>
    <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>
  </span>
);

const ResearchNote = () => (null); // not used; placeholder removed

const OutlineRail = () => {
  const { THESIS_OUTLINE } = window.DOTHESIS;
  return (
    <div style={{
      borderRight: "1px solid var(--ink-100)",
      background: "var(--ink-50)",
      padding: "32px 22px",
    }}>
      <div className="eyebrow">Outline</div>
      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 2 }}>
        {THESIS_OUTLINE.map((ch) => (
          <React.Fragment key={ch.num}>
            <OutlineLink ch={ch} depth={0} />
            {ch.sub && ch.sub.map((s) => (
              <OutlineLink ch={s} depth={1} key={s.num} />
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

const OutlineLink = ({ ch, depth }) => {
  const isDone = ch.status === "ok";
  const isActive = ch.status === "running";
  return (
    <button style={{
      display: "grid",
      gridTemplateColumns: "24px 1fr 10px",
      alignItems: "center",
      gap: 6,
      padding: "8px 8px",
      paddingLeft: 8 + depth * 14,
      borderRadius: 8,
      border: "none",
      background: isActive ? "var(--blue-50)" : "transparent",
      textAlign: "left",
      fontFamily: "var(--font-sans)",
      fontSize: 12.5,
      fontWeight: depth === 0 ? 700 : 500,
      color: isDone ? "var(--ink-800)" : isActive ? "var(--blue-600)" : "var(--ink-400)",
      cursor: "pointer",
    }}>
      <span style={{ fontFamily: "var(--font-serif)", fontWeight: 600, color: "var(--ink-400)" }}>{ch.num}.</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ch.title}</span>
      {isDone && <Icon name="check" size={10} stroke={3} style={{ color: "var(--ok-fg)" }} />}
      {isActive && <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--blue-600)" }} />}
    </button>
  );
};

const CitationRail = ({ activeCite, formatInline }) => {
  const { CITATIONS } = window.DOTHESIS;
  const cited = CITATIONS.slice(0, 5);
  return (
    <div style={{ padding: "32px 24px", background: "var(--ink-50)" }}>
      <div className="eyebrow">Cited on this page</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
        {cited.map((c) => (
          <CitedItem key={c.key} c={c} active={activeCite === c.key} formatInline={formatInline} />
        ))}
      </div>
      <hr className="hr" style={{ margin: "20px 0" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 32, height: 32, background: "var(--ok-bg)", color: "var(--ok-fg)",
          borderRadius: 10, display: "grid", placeItems: "center",
        }}>
          <Icon name="shield" size={16} stroke={2.5} />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>32 / 32 verified</div>
          <div style={{ fontSize: 11, color: "var(--ink-500)" }}>Across CrossRef, OpenAlex, Semantic Scholar, arXiv</div>
        </div>
      </div>
    </div>
  );
};

const CitedItem = ({ c, active, formatInline }) => (
  <div style={{
    background: active ? "var(--blue-50)" : "var(--paper)",
    border: `1px solid ${active ? "var(--blue-100)" : "var(--ink-100)"}`,
    borderRadius: 12,
    padding: 12,
    transition: "background 0.15s",
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
      <span style={{
        fontSize: 10, fontWeight: 800, letterSpacing: "0.06em",
        color: "var(--ok-fg)", background: "var(--ok-bg)",
        padding: "2px 6px", borderRadius: 999,
      }}>
        ✓ {c.source}
      </span>
      <span style={{ fontSize: 10.5, color: "var(--ink-400)", fontFamily: "var(--font-mono)" }}>
        {formatInline(c.key, c.year, c.authors)}
      </span>
    </div>
    <div style={{ fontFamily: "var(--font-serif)", fontSize: 13, fontWeight: 600, lineHeight: 1.35, color: "var(--ink-900)" }}>
      {c.title}
    </div>
    <div style={{ fontSize: 11.5, color: "var(--ink-500)", marginTop: 4 }}>
      {c.authors.split(",").slice(0, 2).join(", ")} <span style={{ color: "var(--ink-400)" }}>({c.year})</span>
    </div>
  </div>
);

window.DraftEditor = DraftEditor;
