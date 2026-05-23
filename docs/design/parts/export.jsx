// Export — PDF / DOCX / LaTeX

const Export = ({ go, citationStyle = "APA" }) => {
  const { Card } = window.SHARED;
  const [format, setFormat] = useState("pdf");
  const [opts, setOpts] = useState({
    tableOfContents: true,
    titlePage: true,
    pageNumbers: true,
    twoColumn: false,
    lineSpacing: 1.5,
    figureCaptions: true,
    inlineComments: false,
  });

  const formats = [
    { id: "pdf",   label: "PDF",          desc: "LaTeX-typeset, journal-ready",  size: "1.8 MB", icon: "doc-pdf", color: "#d22a2a" },
    { id: "docx",  label: "Word (.docx)", desc: "Editable, tracked changes",     size: "612 KB",  icon: "doc-word", color: "#1c2eff" },
    { id: "latex", label: "LaTeX source", desc: "For arXiv, journal submission", size: "180 KB",  icon: "doc-tex",  color: "#0a8a55" },
    { id: "md",    label: "Markdown",     desc: "Plain text + bibliography",     size: "92 KB",   icon: "doc",      color: "#5b3aa8" },
  ];

  return (
    <div className="canvas">
      <div>
        <div className="eyebrow">Export · {citationStyle} bibliography</div>
        <div className="section-title" style={{ fontSize: 22, marginTop: 6 }}>
          Ship your <span style={{ color: "var(--blue-600)" }}>finished draft.</span>
        </div>
        <p className="page-subtitle" style={{ maxWidth: 720 }}>
          Compositor renders your markdown to the chosen format via Pandoc + LaTeX. Citations are
          re-compiled with your selected style before each export.
        </p>
      </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 24, alignItems: "flex-start" }}>
          {/* Left: format + options */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <Card title="Choose a format">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {formats.map((f) => (
                  <button
                    key={f.id}
                    className={`choice ${format === f.id ? "selected" : ""}`}
                    onClick={() => setFormat(f.id)}
                    style={{ padding: 18 }}
                  >
                    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 12,
                        background: `${f.color}18`, color: f.color,
                        display: "grid", placeItems: "center",
                      }}>
                        <Icon name={f.icon} size={22} />
                      </div>
                      <div style={{ textAlign: "left" }}>
                        <div className="choice-title">{f.label}</div>
                        <div className="choice-desc">{f.desc}</div>
                      </div>
                    </div>
                    <div style={{
                      marginTop: 12, display: "flex", justifyContent: "space-between",
                      fontSize: 11.5, color: "var(--ink-500)", fontWeight: 600,
                    }}>
                      <span>~{f.size}</span>
                      <span>Generated in &lt; 8s</span>
                    </div>
                  </button>
                ))}
              </div>
            </Card>

            <Card title="Formatting options">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <Switch label="Title page" desc="Includes university, advisor, abstract"
                        on={opts.titlePage} onChange={(v) => setOpts({ ...opts, titlePage: v })} />
                <Switch label="Table of contents" desc="Auto-generated from chapter outline"
                        on={opts.tableOfContents} onChange={(v) => setOpts({ ...opts, tableOfContents: v })} />
                <Switch label="Page numbers" desc="Roman for front matter, arabic for body"
                        on={opts.pageNumbers} onChange={(v) => setOpts({ ...opts, pageNumbers: v })} />
                <Switch label="Two-column layout" desc="For journal submission (IEEE / ACM)"
                        on={opts.twoColumn} onChange={(v) => setOpts({ ...opts, twoColumn: v })} />
                <Switch label="Figure captions" desc="Auto-number figures and tables"
                        on={opts.figureCaptions} onChange={(v) => setOpts({ ...opts, figureCaptions: v })} />
                <Switch label="Include inline agent comments" desc="Keeps QA notes as PDF margin annotations"
                        on={opts.inlineComments} onChange={(v) => setOpts({ ...opts, inlineComments: v })} />
              </div>

              <hr className="hr" style={{ margin: "20px 0" }} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="field">
                  <label>Line spacing</label>
                  <select value={opts.lineSpacing} onChange={(e) => setOpts({ ...opts, lineSpacing: parseFloat(e.target.value) })}>
                    <option value={1.0}>1.0 (single)</option>
                    <option value={1.15}>1.15</option>
                    <option value={1.5}>1.5 (recommended)</option>
                    <option value={2.0}>2.0 (double)</option>
                  </select>
                </div>
                <div className="field">
                  <label>Body font</label>
                  <select defaultValue="serif">
                    <option value="serif">Source Serif 4 (default)</option>
                    <option>EB Garamond</option>
                    <option>Times New Roman</option>
                    <option>Computer Modern (LaTeX)</option>
                  </select>
                </div>
              </div>
            </Card>

            <Card title="Pre-flight checks" subtitle="What the agents would tell your advisor.">
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <Check status="ok" label="All 32 citations verified" detail="100% of in-text references resolve to real DOIs." />
                <Check status="ok" label="No contradictions across chapters" detail="Thread agent ran a final pass 14 minutes ago." />
                <Check status="ok" label="Voice & tense consistent" detail="Narrator detected zero shifts." />
                <Check status="warn" label="2 hedging opportunities flagged" detail="§4.2 — verbs 'will' / 'must' may be too strong for a comparative claim." />
                <Check status="ok" label="Word count on target" detail="14,820 of 27,000 (you can ship as a chapter-grade interim too)." />
              </div>
            </Card>
          </div>

          {/* Right rail: preview + go */}
          <div style={{ position: "sticky", top: 96, display: "flex", flexDirection: "column", gap: 14 }}>
            <Card padded={false}>
              <div style={{
                padding: 24,
                background: "linear-gradient(180deg, #f8f7f2 0%, #ffffff 80%)",
                borderRadius: "18px 18px 0 0",
                aspectRatio: "1 / 1.414",
                position: "relative",
                overflow: "hidden",
              }}>
                {/* Mini PDF preview */}
                <div style={{
                  position: "absolute", inset: 16, background: "white",
                  boxShadow: "0 18px 40px -20px rgba(0,0,0,0.18)",
                  borderRadius: 4, padding: "28px 22px",
                  fontFamily: "var(--font-serif)",
                  overflow: "hidden",
                }}>
                  <div style={{ fontSize: 9, color: "#7a7066", letterSpacing: 1, textTransform: "uppercase", textAlign: "center" }}>
                    Master's Thesis · Faculty of Public Affairs
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.2, marginTop: 20, textAlign: "center" }}>
                    Algorithmic Decision-Making and Democratic Accountability
                  </div>
                  <div style={{ fontSize: 9, fontStyle: "italic", color: "#666", marginTop: 6, textAlign: "center", lineHeight: 1.3 }}>
                    A Comparative Study of EU and US Regulatory Frameworks
                  </div>
                  <hr style={{ border: "none", borderTop: "1px solid #e5e2da", margin: "16px 14px" }} />
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                    <div key={i} style={{
                      height: 5,
                      background: "#ebe8e0",
                      margin: "5px 0",
                      borderRadius: 2,
                      width: `${88 - (i % 3) * 18}%`,
                    }} />
                  ))}
                  <div style={{ height: 6 }} />
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={"b" + i} style={{
                      height: 5,
                      background: "#ebe8e0",
                      margin: "5px 0",
                      borderRadius: 2,
                      width: `${92 - (i % 4) * 10}%`,
                    }} />
                  ))}
                  <div style={{ position: "absolute", bottom: 16, left: 0, right: 0, textAlign: "center", fontSize: 8, color: "#999" }}>
                    1
                  </div>
                </div>
              </div>
              <div style={{ padding: 20 }}>
                <div className="eyebrow">Preview</div>
                <div style={{ fontWeight: 700, marginTop: 4 }}>
                  {formats.find((f) => f.id === format).label} · 87 pages
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4 }}>
                  Front matter (3) · Body (78) · Bibliography (6)
                </div>
                <button className="btn btn-primary btn-block btn-lg" style={{ marginTop: 14 }}>
                  <Icon name="export" size={16} stroke={2.5}/> Generate {formats.find((f) => f.id === format).label}
                </button>
                <button className="btn btn-ghost btn-block btn-sm" style={{ marginTop: 6 }}>
                  Email me when ready
                </button>
              </div>
            </Card>

            <div style={{
              background: "var(--ink-900)", color: "white",
              borderRadius: 14, padding: 18,
            }}>
              <div className="eyebrow" style={{ color: "rgba(255,255,255,0.6)" }}>Tip</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 6 }}>
                Submitting to a specific journal?
              </div>
              <div style={{ fontSize: 12.5, color: "rgba(255,255,255,0.7)", marginTop: 6, lineHeight: 1.5 }}>
                We have ready-made LaTeX templates for IEEE, ACM, Elsevier, Springer LNCS, and Nature.
                Pick one and Compositor swaps the class file for you.
              </div>
              <button className="btn btn-sm" style={{
                marginTop: 12, background: "white", color: "var(--ink-900)",
              }}>Browse templates</button>
            </div>
          </div>
        </div>
      </div>
  );
};

const Switch = ({ label, desc, on, onChange }) => (
  <button
    onClick={() => onChange(!on)}
    style={{
      display: "flex", gap: 12, padding: 14,
      border: "1.5px solid var(--ink-200)",
      borderRadius: 12,
      background: "var(--paper)",
      textAlign: "left",
      cursor: "pointer",
      alignItems: "flex-start",
    }}
  >
    <div style={{
      width: 36, height: 22, borderRadius: 999,
      background: on ? "var(--blue-600)" : "var(--ink-200)",
      position: "relative", flexShrink: 0, transition: "background 0.15s",
    }}>
      <div style={{
        position: "absolute", top: 2, left: on ? 16 : 2,
        width: 18, height: 18, borderRadius: 999, background: "white",
        transition: "left 0.15s",
        boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
      }}/>
    </div>
    <div>
      <div style={{ fontSize: 13, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 2, lineHeight: 1.4 }}>{desc}</div>
    </div>
  </button>
);

const Check = ({ status, label, detail }) => {
  const isOk = status === "ok";
  const c = isOk ? { bg: "var(--ok-bg)", fg: "var(--ok-fg)" } : { bg: "var(--pause-bg)", fg: "var(--pause-fg)" };
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <div style={{
        width: 26, height: 26, borderRadius: 8,
        background: c.bg, color: c.fg,
        display: "grid", placeItems: "center", flexShrink: 0,
      }}>
        <Icon name={isOk ? "check" : "warning"} size={14} stroke={3} />
      </div>
      <div>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>{label}</div>
        <div style={{ fontSize: 12.5, color: "var(--ink-500)", marginTop: 2, lineHeight: 1.45 }}>{detail}</div>
      </div>
    </div>
  );
};

window.Export = Export;
