"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Icon } from "./icons";
import { Topbar } from "./shared";
import { apiFetch } from "../lib/api";

const LANG_TO_CODE = {
  "English": "en",
  "Spanish": "es",
  "German": "de",
  "French": "fr",
  "Mandarin": "zh",
  "Japanese": "ja",
  "Vietnamese": "vi",
};

const STYLE_TO_API = {
  "APA 7th": "apa",
  "MLA 9th": "mla",
  "Chicago": "chicago",
  "IEEE": "ieee",
  "Harvard": "harvard",
};

const LENGTH_TO_LEVEL = {
  "5–10 pages": "research",
  "10–15 pages": "bachelor",
  "25–30 pages (Master's)": "master",
  "50–80 pages (PhD)": "phd",
};

const SAMPLE_TOPICS = [
  "AI in healthcare diagnostics",
  "Climate change mitigation strategies",
  "Machine learning in finance",
  "Behavioral economics in policy",
  "Renewable energy adoption in Southeast Asia",
  "Vietnamese startup ecosystem post-pandemic",
];

export const Wizard = () => {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [tab, setTab] = useState("notes");
  const [notes, setNotes] = useState("");
  const [language, setLanguage] = useState("English");
  const [citationStyle, setCitationStyle] = useState("APA 7th");
  const [length, setLength] = useState("25–30 pages (Master's)");
  const [model] = useState("claude-sonnet");
  const [hideContext, setHideContext] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const onSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!topic.trim()) {
      setSubmitError({ text: "Please describe your thesis topic before generating." });
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body = {
        topic: topic.trim(),
        research_question: notes.trim() || null,
        academic_level: LENGTH_TO_LEVEL[length] || "master",
        language: LANG_TO_CODE[language] || "en",
        model,
        citation_style: STYLE_TO_API[citationStyle] || "apa",
        sources: {
          crossref: true,
          openalex: true,
          semanticscholar: true,
          arxiv: true,
          jstor: false,
          googleScholar: false,
        },
        tone: "rigorous",
      };
      const resp = await apiFetch("/papers", { method: "POST", body });
      router.push(`/paper/${resp.paper_id}?tab=run`);
    } catch (err) {
      const code = err?.body?.error?.code;
      if (code === "already_running") {
        setSubmitError({
          text: "You already have a thesis running. Stop it or wait for it to finish before starting a new one.",
          actionHref: "/",
          actionLabel: "Go to my drafts",
        });
      } else if (code === "daily_quota") {
        setSubmitError({ text: "Daily limit reached. Try again tomorrow." });
      } else {
        setSubmitError({ text: err.message || "Could not start the job." });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onSubmit();
  };

  return (
    <div className="main">
      <Topbar crumbs={["Workspace", "New Thesis"]} />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "56px 40px 80px",
          background: "var(--ink-50)",
        }}
      >
        <div style={{ width: "100%", maxWidth: 720, textAlign: "center" }}>
          <h1
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: 44,
              fontWeight: 800,
              letterSpacing: "-0.025em",
              margin: 0,
              lineHeight: 1.05,
            }}
          >
            Your AI <span style={{ color: "var(--blue-600)" }}>research team.</span>
          </h1>
          <div
            style={{
              marginTop: 18,
              display: "inline-flex",
              gap: 28,
              flexWrap: "wrap",
              justifyContent: "center",
              fontSize: 14,
              fontWeight: 600,
              color: "var(--ink-700)",
            }}
          >
            <Tick>Full paper in 10–20 minutes</Tick>
            <Tick>Every citation verified</Tick>
            <Tick>Your writing, your style</Tick>
          </div>
        </div>

        {/* Composer */}
        <form
          onSubmit={onSubmit}
          style={{
            width: "100%",
            maxWidth: 720,
            marginTop: 36,
            background: "var(--paper)",
            border: "1.5px solid var(--ink-200)",
            borderRadius: 18,
            boxShadow: "var(--shadow-card)",
          }}
        >
          <div style={{ padding: "20px 22px 6px" }}>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Describe your research topic…"
              maxLength={500}
              autoFocus
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
          <div
            style={{
              padding: "10px 18px 14px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
              borderTop: "1px solid var(--ink-100)",
            }}
          >
            <ChipBtn icon="doc" onClick={() => setHideContext((v) => !v)}>
              {hideContext ? "Add context" : "Hide context"}
            </ChipBtn>
            <span style={{ fontSize: 12, color: "var(--ink-400)" }}>Optional</span>
            <div
              style={{
                marginLeft: "auto",
                fontSize: 12,
                color: "var(--ink-400)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {topic.length}/500
            </div>
          </div>

          {/* Context section (collapsible) */}
          {!hideContext && (
            <div style={{ padding: "14px 22px 18px", borderTop: "1px solid var(--ink-100)" }}>
              <div style={{ fontSize: 12, color: "var(--ink-500)", marginBottom: 10 }}>
                Add a research question or notes to guide generation.
              </div>
              <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
                <MiniTab on={tab === "notes"} onClick={() => setTab("notes")}>
                  Notes
                </MiniTab>
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Research question, constraints, key points, style/tone instructions…"
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
              <div
                style={{
                  marginTop: 8,
                  fontSize: 11.5,
                  color: "var(--ink-400)",
                }}
              >
                {notes.length.toLocaleString()} / 30,000 characters
              </div>
            </div>
          )}
        </form>

        {/* Sample topic chips — shown until the user starts typing */}
        {topic.trim().length === 0 && (
          <div
            style={{
              width: "100%",
              maxWidth: 720,
              marginTop: 18,
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              justifyContent: "center",
            }}
          >
            {SAMPLE_TOPICS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setTopic(s)}
                style={{
                  padding: "8px 14px",
                  borderRadius: 999,
                  border: "1.5px solid var(--ink-200)",
                  background: "var(--paper)",
                  color: "var(--ink-700)",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "border-color 0.12s, color 0.12s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--blue-600)";
                  e.currentTarget.style.color = "var(--blue-600)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--ink-200)";
                  e.currentTarget.style.color = "var(--ink-700)";
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Settings row */}
        <div
          style={{
            marginTop: 28,
            display: "inline-flex",
            gap: 24,
            alignItems: "center",
            flexWrap: "wrap",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--ink-800)",
          }}
        >
          <DropPick value={language} options={Object.keys(LANG_TO_CODE)} onChange={setLanguage} />
          <DropPick
            value={citationStyle}
            options={Object.keys(STYLE_TO_API)}
            onChange={setCitationStyle}
          />
          <DropPick value={length} options={Object.keys(LENGTH_TO_LEVEL)} onChange={setLength} />
        </div>

        {/* CTA */}
        <button
          type="button"
          onClick={onSubmit}
          className="btn btn-primary btn-lg"
          disabled={submitting}
          style={{
            marginTop: 22,
            padding: "20px 28px",
            fontSize: 16,
            minWidth: 420,
            opacity: submitting ? 0.7 : 1,
          }}
        >
          {submitting ? "Starting…" : "Generate Paper"}{" "}
          <Icon name="arrow-right" size={16} stroke={2.5} />
        </button>

        <div style={{ marginTop: 10, fontSize: 12, color: "var(--ink-500)" }}>
          <span className="kbd">⌘/Ctrl</span> + <span className="kbd">Enter</span> to submit
        </div>

        {submitError && (
          <div
            style={{
              marginTop: 16,
              maxWidth: 520,
              padding: 14,
              background: "var(--stop-bg)",
              color: "var(--stop-fg)",
              borderRadius: 12,
              fontSize: 13,
              lineHeight: 1.5,
              textAlign: "center",
            }}
          >
            {submitError.text}
            {submitError.actionHref && (
              <div style={{ marginTop: 6 }}>
                <Link
                  href={submitError.actionHref}
                  style={{ color: "var(--blue-600)", fontWeight: 700 }}
                >
                  {submitError.actionLabel} →
                </Link>
              </div>
            )}
          </div>
        )}
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
    type="button"
    onClick={onClick}
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "7px 12px",
      borderRadius: 10,
      border: "1.5px solid var(--ink-200)",
      background: "var(--paper)",
      fontSize: 13,
      fontWeight: 600,
      color: "var(--ink-700)",
      cursor: "pointer",
    }}
  >
    <Icon name={icon} size={14} /> {children}
  </button>
);

const MiniTab = ({ on, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    style={{
      padding: "6px 12px",
      borderRadius: 8,
      border: "none",
      background: on ? "var(--ok-bg)" : "transparent",
      color: on ? "var(--ok-fg)" : "var(--ink-500)",
      fontSize: 12.5,
      fontWeight: 700,
      cursor: "pointer",
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
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 10px",
          border: "none",
          background: "transparent",
          fontSize: 14,
          fontWeight: 700,
          color: "var(--ink-900)",
          cursor: "pointer",
          borderRadius: 8,
        }}
      >
        {value}{" "}
        <Icon name="chevron-down" size={14} stroke={2.2} style={{ color: "var(--ink-400)" }} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 30 }} onClick={() => setOpen(false)} />
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              left: 0,
              background: "var(--paper)",
              borderRadius: 12,
              border: "1px solid var(--ink-100)",
              boxShadow: "var(--shadow-pop)",
              minWidth: 180,
              padding: 6,
              zIndex: 40,
            }}
          >
            {options.map((o) => (
              <button
                key={o}
                type="button"
                onClick={() => {
                  onChange(o);
                  setOpen(false);
                }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 12px",
                  border: "none",
                  background: o === value ? "var(--blue-50)" : "transparent",
                  color: o === value ? "var(--blue-600)" : "var(--ink-800)",
                  fontSize: 13.5,
                  fontWeight: 600,
                  borderRadius: 8,
                  cursor: "pointer",
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
