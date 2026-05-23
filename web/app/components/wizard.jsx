"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "./icons";
import { Topbar, Card } from "./shared";
import { apiFetch } from "../lib/api";

const LEVELS = [
  { id: "research", label: "Research paper", desc: "3k–5k words · 10+ citations · 3–4 chapters", words: "3k–5k", icon: "doc" },
  { id: "bachelor", label: "Bachelor's thesis", desc: "10k–15k words · 15+ citations · 5–7 chapters", words: "10k–15k", icon: "graduation" },
  { id: "master", label: "Master's thesis", desc: "25k–30k words · 25+ citations · 7–10 chapters", words: "25k–30k", icon: "graduation" },
  { id: "phd", label: "PhD dissertation", desc: "50k–80k words · 50+ citations · 10–15 chapters", words: "50k–80k", icon: "library" },
];

const MODELS = [
  { id: "gemini-flash", label: "Gemini Flash", cost: "35 credits", speed: "Fast", quality: "Good", note: "Best for first drafts" },
  { id: "claude-sonnet", label: "Claude Sonnet 4.5", cost: "140 credits", speed: "Balanced", quality: "Excellent", note: "Recommended" },
  { id: "claude-opus", label: "Claude Opus", cost: "300 credits", speed: "Slower", quality: "Outstanding", note: "PhD / publication grade" },
  { id: "gpt-5", label: "GPT-5", cost: "210 credits", speed: "Balanced", quality: "Excellent", note: "Strong reasoning" },
];

export const Wizard = () => {
  const router = useRouter();
  const [topic, setTopic] = useState("Algorithmic decision-making and democratic accountability: a comparative study of EU and US regulatory frameworks");
  const [question, setQuestion] = useState("How do the EU AI Act and the US sectoral approach diverge on enforcement of algorithmic decisions in public administration, and what does that imply for transatlantic harmonization?");
  const [level, setLevel] = useState("master");
  const [language, setLanguage] = useState("English (Academic)");
  const [model, setModel] = useState("claude-sonnet");
  const [citationStyle, setCitationStyle] = useState("apa");
  const [sources, setSources] = useState({
    crossref: true, openalex: true, semanticscholar: true, arxiv: true, jstor: false, googleScholar: false,
  });
  const [tone, setTone] = useState("rigorous");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const langToCode = (l) => {
    const x = (l || "").toLowerCase();
    if (x.startsWith("english")) return "en";
    if (x.startsWith("spanish")) return "es";
    if (x.startsWith("german")) return "de";
    if (x.startsWith("french")) return "fr";
    if (x.startsWith("mandarin")) return "zh";
    if (x.startsWith("japanese")) return "ja";
    return "en";
  };

  const start = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body = {
        topic,
        research_question: question,
        academic_level: level,
        language: langToCode(language),
        model,
        citation_style: citationStyle,
        sources,
        tone,
      };
      const resp = await apiFetch("/papers", { method: "POST", body });
      router.push(`/paper/${resp.paper_id}?tab=run`);
    } catch (e) {
      const code = e?.body?.error?.code;
      if (code === "already_running") {
        setSubmitError({
          text: "You already have a thesis running. Stop it from its page (or wait for it to finish) before starting a new one.",
          actionHref: "/",
          actionLabel: "Go to my drafts",
        });
      } else if (code === "daily_quota") {
        setSubmitError({ text: "Daily limit reached (3 jobs / day). Try again tomorrow." });
      } else {
        setSubmitError({ text: e.message || "Could not start the job." });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const SourceTile = ({ id, label, n }) => (
    <button
      className={`choice ${sources[id] ? "selected" : ""}`}
      onClick={() => setSources((s) => ({ ...s, [id]: !s[id] }))}
      style={{ padding: 14 }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="choice-title">
          <Icon name="library" size={14} /> {label}
        </div>
        <div style={{
          width: 18, height: 18, borderRadius: 6,
          background: sources[id] ? "var(--blue-600)" : "transparent",
          border: sources[id] ? "none" : "1.5px solid var(--ink-300)",
          display: "grid", placeItems: "center",
        }}>
          {sources[id] && <Icon name="check" size={12} stroke={3} style={{ color: "white" }} />}
        </div>
      </div>
      <div className="choice-desc">{n} indexed papers</div>
    </button>
  );

  return (
    <div className="main">
      <Topbar crumbs={["Workspace", "New Thesis"]} />
      <div className="canvas">
        <div>
          <div className="eyebrow">New draft · Step 1 of 1</div>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            Set up your <span className="accent">thesis brief.</span>
          </h1>
          <p className="page-subtitle">
            The clearer your research question, the better your draft. You can change any of this later.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 20, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Card title="Topic & research question">
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div className="field">
                  <label>Working title</label>
                  <input value={topic} onChange={(e) => setTopic(e.target.value)} />
                  <span className="hint">Use sentence case. We&apos;ll polish this in the abstract pass.</span>
                </div>
                <div className="field">
                  <label>Primary research question</label>
                  <textarea value={question} onChange={(e) => setQuestion(e.target.value)} />
                  <span className="hint">One sentence. Specific verbs (&quot;compare&quot;, &quot;evaluate&quot;, &quot;measure&quot;) beat vague ones.</span>
                </div>
              </div>
            </Card>

            <Card title="Academic level" subtitle="Sets word count, chapters, and minimum citations.">
              <div className="choice-grid">
                {LEVELS.map((l) => (
                  <button
                    key={l.id}
                    className={`choice ${level === l.id ? "selected" : ""}`}
                    onClick={() => setLevel(l.id)}
                  >
                    <div className="choice-title">
                      <Icon name={l.icon} size={14} /> {l.label}
                    </div>
                    <div className="choice-desc">{l.desc}</div>
                  </button>
                ))}
              </div>
            </Card>

            <Card title="Sources to search" subtitle="OpenDraft runs a cascade across these databases.">
              <div className="choice-grid">
                <SourceTile id="crossref" label="CrossRef" n="135M" />
                <SourceTile id="openalex" label="OpenAlex" n="245M" />
                <SourceTile id="semanticscholar" label="Semantic Scholar" n="218M" />
                <SourceTile id="arxiv" label="arXiv" n="2.4M" />
                <SourceTile id="jstor" label="JSTOR" n="12M (Pro)" />
                <SourceTile id="googleScholar" label="Google Scholar" n="200M (beta)" />
              </div>
            </Card>

            <Card title="Writing model">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {MODELS.map((m) => (
                  <button
                    key={m.id}
                    className={`choice ${model === m.id ? "selected" : ""}`}
                    onClick={() => setModel(m.id)}
                    style={{ padding: 16 }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div className="choice-title"><Icon name="sparkle" size={14} /> {m.label}</div>
                      {m.note === "Recommended" && (
                        <span style={{
                          background: "var(--blue-600)", color: "white",
                          fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999, letterSpacing: 0.4,
                        }}>RECOMMENDED</span>
                      )}
                    </div>
                    <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 12, alignItems: "center", flexWrap: "wrap" }}>
                      <span><b style={{ color: "var(--ink-900)" }}>{m.cost}</b> <span style={{ color: "var(--ink-400)" }}>/ draft</span></span>
                      <span style={{ color: "var(--ink-400)" }}>·</span>
                      <span style={{ color: "var(--ink-500)" }}>{m.speed} · {m.quality}</span>
                    </div>
                    {m.note !== "Recommended" && (
                      <div className="choice-desc" style={{ marginTop: 6 }}>{m.note}</div>
                    )}
                  </button>
                ))}
              </div>
            </Card>

            <Card title="Style & language">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                <div className="field">
                  <label>Citation style</label>
                  <select value={citationStyle} onChange={(e) => setCitationStyle(e.target.value)}>
                    <option value="apa">APA</option>
                    <option value="mla">MLA</option>
                    <option value="chicago">Chicago</option>
                    <option value="ieee">IEEE</option>
                    <option value="harvard">Harvard</option>
                  </select>
                </div>
                <div className="field">
                  <label>Language</label>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                    <option>English (Academic)</option>
                    <option>Spanish</option>
                    <option>German</option>
                    <option>French</option>
                    <option>Mandarin Chinese</option>
                    <option>Japanese</option>
                  </select>
                </div>
                <div className="field">
                  <label>Tone</label>
                  <select value={tone} onChange={(e) => setTone(e.target.value)}>
                    <option value="rigorous">Rigorous · cautious</option>
                    <option value="argumentative">Argumentative</option>
                    <option value="descriptive">Descriptive</option>
                    <option value="empirical">Empirical · data-led</option>
                  </select>
                </div>
              </div>
            </Card>
          </div>

          <div style={{ position: "sticky", top: 96, display: "flex", flexDirection: "column", gap: 12 }}>
            <Card padded={false}>
              <div style={{ padding: 20 }}>
                <div className="eyebrow">Your brief</div>
                <div style={{ fontFamily: "var(--font-serif)", fontSize: 20, lineHeight: 1.3, marginTop: 10, fontWeight: 600 }}>
                  {topic.slice(0, 110)}{topic.length > 110 ? "…" : ""}
                </div>
                <hr className="hr" style={{ margin: "16px 0" }} />
                <Row k="Level" v={LEVELS.find((l) => l.id === level).label} />
                <Row k="Target length" v={LEVELS.find((l) => l.id === level).words + " words"} />
                <Row k="Citations" v={citationStyle.toUpperCase() + " · 25+ verified"} />
                <Row k="Sources" v={Object.values(sources).filter(Boolean).length + " databases"} />
                <Row k="Language" v={language} />
                <Row k="Model" v={MODELS.find((m) => m.id === model).label} />
                <Row k="Est. cost" v={MODELS.find((m) => m.id === model).cost} highlight />
                <Row k="Balance after" v={`${(5756 - parseInt(MODELS.find((m) => m.id === model).cost)).toLocaleString()} credits`} />
                <Row k="Est. time" v="12–18 min" />
              </div>
              <hr className="hr" />
              <div style={{ padding: 20 }}>
                <button
                  className="btn btn-primary btn-block btn-lg"
                  onClick={start}
                  disabled={submitting}
                >
                  <Icon name="play" size={16} stroke={2.5} />
                  {submitting ? "Starting…" : "Start agent pipeline"}
                </button>
                {submitError && (
                  <div style={{
                    marginTop: 10, padding: 10, borderRadius: 8,
                    background: "var(--danger-bg, #fde2e2)",
                    color: "var(--danger-fg, #b91c1c)",
                    fontSize: 12, lineHeight: 1.5,
                  }}>
                    {submitError.text}
                    {submitError.actionHref && (
                      <div style={{ marginTop: 6 }}>
                        <a href={submitError.actionHref} style={{ color: "var(--blue-600)", fontWeight: 700 }}>
                          {submitError.actionLabel} →
                        </a>
                      </div>
                    )}
                  </div>
                )}
                <button className="btn btn-ghost btn-block btn-sm" style={{ marginTop: 6 }}>
                  Save brief as draft
                </button>
              </div>
            </Card>

            <div style={{
              background: "var(--blue-50)", border: "1px solid var(--blue-100)",
              borderRadius: 14, padding: 16, fontSize: 12, color: "var(--ink-700)", lineHeight: 1.5,
            }}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <Icon name="shield" size={16} stroke={2} style={{ color: "var(--blue-600)", marginTop: 1, flexShrink: 0 }} />
                <div>
                  <b>Every citation is verified.</b> If a paper doesn&apos;t return a DOI on CrossRef or OpenAlex, it doesn&apos;t make the bibliography. No hallucinated sources.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const Row = ({ k, v, highlight }) => (
  <div style={{
    display: "flex", justifyContent: "space-between", padding: "7px 0",
    fontSize: 13,
  }}>
    <span style={{ color: "var(--ink-500)" }}>{k}</span>
    <span style={{ fontWeight: 700, color: highlight ? "var(--blue-600)" : "var(--ink-900)" }}>{v}</span>
  </div>
);
