// New Thesis wizard — minimal, prompt-first.

const Wizard = ({ go }) => {
  const [topic, setTopic] = useState(
    "A comparative analysis of algorithmic decision-making in EU and US public administrations: effectiveness, accountability, and democratic legitimacy of the EU AI Act versus the US sectoral framework."
  );
  const [tab, setTab] = useState("notes");
  const [notes, setNotes] = useState("");
  const [language, setLanguage] = useState("English");
  const [citationStyle, setCitationStyle] = useState("APA 7th");
  const [length, setLength] = useState("10–15 pages");
  const [hideContext, setHideContext] = useState(false);

  const lengthCost = { "5–10 pages": 1, "10–15 pages": 1, "20–30 pages (Master's)": 2, "50–80 pages (PhD)": 4 };
  const cost = lengthCost[length] || 1;
  const balance = 9;

  return (
    <div className="main">
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "56px 40px 80px",
        background: "var(--ink-50)",
      }}>
        <div style={{ width: "100%", maxWidth: 720, textAlign: "center" }}>
          <h1 style={{
            fontFamily: "var(--font-sans)",
            fontSize: 44,
            fontWeight: 800,
            letterSpacing: "-0.025em",
            margin: 0,
            lineHeight: 1.05,
          }}>
            Your AI <span style={{ color: "var(--blue-600)" }}>research team.</span>
          </h1>
          <div style={{
            marginTop: 18,
            display: "inline-flex",
            gap: 28,
            flexWrap: "wrap",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--ink-700)",
          }}>
            <Tick>Full paper in 10 minutes</Tick>
            <Tick>Every citation verified</Tick>
            <Tick>Your writing, your style</Tick>
          </div>
        </div>

        {/* Composer */}
        <div style={{
          width: "100%",
          maxWidth: 720,
          marginTop: 36,
          background: "var(--paper)",
          border: "1.5px solid var(--ink-200)",
          borderRadius: 18,
          boxShadow: "var(--shadow-card)",
        }}>
          {/* Topic */}
          <div style={{ padding: "20px 22px 6px" }}>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="What's your thesis about?"
              maxLength={500}
              style={{
                width: "100%",
                border: "none",
                outline: "none",
                background: "transparent",
                fontFamily: "var(--font-sans)",
                fontSize: 16,
                lineHeight: 1.55,
                color: "var(--ink-900)",
                resize: "none",
                minHeight: 96,
              }}
            />
          </div>

          {/* Compose controls row */}
          <div style={{
            padding: "10px 18px 14px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            borderTop: "1px solid var(--ink-100)",
          }}>
            <ChipBtn icon="link">Attach</ChipBtn>
            <ChipBtn icon="doc" onClick={() => setHideContext((v) => !v)}>
              {hideContext ? "Show context" : "Hide context"}
            </ChipBtn>
            <span style={{ fontSize: 12, color: "var(--ink-400)" }}>Optional</span>
            <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-400)", fontVariantNumeric: "tabular-nums" }}>
              {topic.length}/500
            </div>
          </div>

          {/* Context section (collapsible) */}
          {!hideContext && (
            <div style={{ padding: "14px 22px 18px", borderTop: "1px solid var(--ink-100)" }}>
              <div style={{ fontSize: 12, color: "var(--ink-500)", marginBottom: 10 }}>
                Add notes and references to guide generation.
              </div>
              <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
                <MiniTab on={tab === "notes"} onClick={() => setTab("notes")}>Notes</MiniTab>
                <MiniTab on={tab === "refs"} onClick={() => setTab("refs")}>References</MiniTab>
              </div>
              {tab === "notes" ? (
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Research notes, constraints, key points, style/tone instructions…"
                  maxLength={30000}
                  style={{
                    width: "100%",
                    minHeight: 110,
                    padding: "12px 14px",
                    border: "1.5px solid var(--ink-200)",
                    borderRadius: 12,
                    outline: "none",
                    fontFamily: "var(--font-sans)",
                    fontSize: 14,
                    lineHeight: 1.55,
                    resize: "vertical",
                    background: "var(--paper)",
                  }}
                />
              ) : (
                <div style={{
                  border: "1.5px dashed var(--ink-200)",
                  borderRadius: 12,
                  padding: "22px 14px",
                  textAlign: "center",
                  fontSize: 13,
                  color: "var(--ink-500)",
                }}>
                  <Icon name="library" size={18} stroke={1.8} style={{ color: "var(--ink-400)" }} />
                  <div style={{ marginTop: 8 }}>
                    Drop a BibTeX file, a Zotero export, or paste a list of DOIs / arXiv IDs.
                  </div>
                  <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }}>
                    <Icon name="plus" size={12} /> Choose file
                  </button>
                </div>
              )}
              <div style={{
                marginTop: 8,
                display: "flex",
                justifyContent: "space-between",
                fontSize: 11.5,
                color: "var(--ink-400)",
              }}>
                <span>{notes.length.toLocaleString()} / 30,000 characters total</span>
                <button style={{
                  background: "none", border: "none", padding: 0, cursor: "pointer",
                  color: "var(--blue-600)", fontSize: 11.5, fontWeight: 600,
                }}>
                  Expand editor
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Tip strip */}
        <div style={{
          width: "100%", maxWidth: 720, marginTop: 18,
          background: "var(--paper)", border: "1px solid var(--ink-100)",
          borderRadius: 12, padding: "12px 16px",
          display: "flex", alignItems: "center", gap: 10,
          fontSize: 13, color: "var(--ink-600)",
        }}>
          <Icon name="sparkle" size={14} style={{ color: "var(--blue-600)" }} />
          <span>Pick a topic, choose your settings, and we'll generate a fully cited research paper in minutes.</span>
          <button style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--ink-400)", cursor: "pointer" }}>
            ×
          </button>
        </div>

        {/* Settings row */}
        <div style={{
          marginTop: 28,
          display: "inline-flex",
          gap: 24,
          alignItems: "center",
          flexWrap: "wrap",
          justifyContent: "center",
          fontSize: 14,
          fontWeight: 600,
          color: "var(--ink-800)",
        }}>
          <DropPick value={language} options={["English", "Spanish", "German", "French", "Mandarin"]}
            onChange={setLanguage} />
          <DropPick value={citationStyle} options={["APA 7th", "MLA 9th", "Chicago", "IEEE", "Harvard"]}
            onChange={setCitationStyle} />
          <DropPick value={length} options={Object.keys(lengthCost)} onChange={setLength} />
          <span style={{ color: "var(--ink-400)" }}>=</span>
          <span style={{ color: "var(--blue-600)", fontWeight: 800 }}>
            {cost} credit{cost === 1 ? "" : "s"}
          </span>
        </div>

        {/* CTA */}
        <button
          className="btn btn-primary btn-lg"
          style={{
            marginTop: 22,
            padding: "20px 28px",
            fontSize: 16,
            minWidth: 420,
            background: "var(--blue-600)",
          }}
          onClick={() => go("paper", { paperId: "alg-gov-2026", tab: "run" })}
        >
          Generate Paper ({cost} credit{cost === 1 ? "" : "s"}) <Icon name="arrow-right" size={16} stroke={2.5} />
        </button>

        <div style={{ marginTop: 10, fontSize: 12, color: "var(--ink-500)" }}>
          <span className="kbd">⌘/Ctrl</span> + <span className="kbd">Enter</span>
        </div>

        <div style={{ marginTop: 18, fontSize: 14, color: "var(--ink-600)" }}>
          You have <b style={{ color: "var(--ink-900)" }}>{balance.toLocaleString()} credits</b>
        </div>
      </div>
    </div>
  );
};

const Tick = ({ children }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
    <Icon name="check" size={14} stroke={3} style={{ color: "var(--ok-fg)" }} />
    {children}
  </span>
);

const ChipBtn = ({ icon, children, onClick }) => (
  <button
    onClick={onClick}
    style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "7px 12px",
      borderRadius: 10,
      border: "1.5px solid var(--ink-200)",
      background: "var(--paper)",
      fontSize: 13, fontWeight: 600,
      color: "var(--ink-700)", cursor: "pointer",
    }}
  >
    <Icon name={icon} size={14} /> {children}
  </button>
);

const MiniTab = ({ on, onClick, children }) => (
  <button
    onClick={onClick}
    style={{
      padding: "6px 12px",
      borderRadius: 8,
      border: "none",
      background: on ? "var(--ok-bg)" : "transparent",
      color: on ? "var(--ok-fg)" : "var(--ink-500)",
      fontSize: 12.5, fontWeight: 700, cursor: "pointer",
    }}
  >
    {children}
  </button>
);

const DropPick = ({ value, options, onChange }) => {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "6px 10px",
          border: "none", background: "transparent",
          fontSize: 14, fontWeight: 700, color: "var(--ink-900)",
          cursor: "pointer", borderRadius: 8,
        }}
      >
        {value} <Icon name="chevron-down" size={14} stroke={2.2} style={{ color: "var(--ink-400)" }} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 30 }} onClick={() => setOpen(false)} />
          <div style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0,
            background: "var(--paper)", borderRadius: 12,
            border: "1px solid var(--ink-100)", boxShadow: "var(--shadow-pop)",
            minWidth: 180, padding: 6, zIndex: 40,
          }}>
            {options.map((o) => (
              <button key={o}
                onClick={() => { onChange(o); setOpen(false); }}
                style={{
                  display: "block", width: "100%", textAlign: "left",
                  padding: "8px 12px", border: "none", background: o === value ? "var(--blue-50)" : "transparent",
                  color: o === value ? "var(--blue-600)" : "var(--ink-800)",
                  fontSize: 13.5, fontWeight: 600, borderRadius: 8, cursor: "pointer",
                }}
              >
                {o}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

window.Wizard = Wizard;
