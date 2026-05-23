"use client";

import useSWR from "swr";
import { swrFetcher } from "../lib/api";
import { useState } from "react";
import { Icon } from "./icons";
import { Card } from "./shared";
import { NotReady } from "./not-ready";

const REJECTED = [
  { title: "Anonymous (2024). The future of AI policy is open source.",
    reason: "No DOI returned by CrossRef, OpenAlex, Semantic Scholar, or arXiv. Verifier could not establish authorship.",
    by: "Verifier" },
  { title: "Lee, K. (2019). Algorithmic governance in China.",
    reason: "Duplicate of an already-verified entry (Lee, K. F. 2019). Citation Compiler de-duplicated automatically.",
    by: "Citation Compiler" },
  { title: "Smith, J. (2022). The transatlantic data divide.",
    reason: "Year mismatch between Scout (2022) and CrossRef (2018). Below Verifier confidence threshold (0.62).",
    by: "Verifier" },
  { title: "OpenAI (2023). GPT-4 technical report.",
    reason: "Removed by you on Mar 14 — replaced with Hacker et al. (2024) for stronger argumentative fit.",
    by: "You" },
];

export const Citations = ({ paperId, citationStyle = "APA" }) => {
  const { data: citations, error, isLoading } = useSWR(
    paperId ? `/papers/${paperId}/citations` : null,
    swrFetcher,
  );
  const [tab, setTab] = useState("verified");

  if (isLoading) return <div style={{ padding: 32 }}>Loading citations…</div>;
  if (error) return <NotReady paperId={paperId} kind="citations" error={error} />;
  const rows = citations || [];

  const tabs = [
    { id: "verified", label: "Verified", count: 32, color: "var(--ok-fg)" },
    { id: "flagged", label: "Conflicts", count: 2, color: "var(--pause-fg)" },
    { id: "rejected", label: "Rejected", count: 4, color: "var(--stop-fg)" },
    { id: "queued", label: "Queued", count: 6, color: "var(--ink-400)" },
  ];

  return (
    <div className="canvas">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div className="eyebrow">Citation manager · {citationStyle}</div>
          <div className="section-title" style={{ fontSize: 22, marginTop: 6 }}>
            <span style={{ color: "var(--blue-600)" }}>32 verified.</span> 2 need your attention.
          </div>
          <p className="page-subtitle" style={{ maxWidth: 720 }}>
            Every source has been checked against at least one open citation database. Swap, override, or remove —
            then re-run Citation Compiler to rewrite the bibliography.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost btn-sm"><Icon name="search" size={12}/> Search bibliography</button>
          <button className="btn btn-secondary btn-sm"><Icon name="plus" size={12}/> Add citation</button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <SourcePill source="CrossRef" n={12} accent="#1c2eff" />
        <SourcePill source="OpenAlex" n={9} accent="#5b3aa8" />
        <SourcePill source="Semantic Scholar" n={8} accent="#0a8a55" />
        <SourcePill source="arXiv" n={3} accent="#6e1d2c" />
      </div>

      <Card padded={false}>
        <div style={{
          display: "flex",
          gap: 6,
          padding: "16px 24px",
          borderBottom: "1px solid var(--ink-100)",
        }}>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: "10px 16px",
                borderRadius: 10,
                border: "none",
                background: tab === t.id ? "var(--ink-50)" : "transparent",
                fontWeight: 700,
                fontSize: 13,
                color: tab === t.id ? "var(--ink-900)" : "var(--ink-500)",
                cursor: "pointer",
                display: "inline-flex",
                gap: 8, alignItems: "center",
              }}
            >
              {t.label}
              <span style={{
                padding: "1px 7px",
                borderRadius: 999,
                background: tab === t.id ? t.color : "var(--ink-100)",
                color: tab === t.id ? "white" : "var(--ink-500)",
                fontSize: 11,
                fontWeight: 800,
              }}>{t.count}</span>
            </button>
          ))}
        </div>

        {tab === "verified" && (
          <table className="table">
            <thead>
              <tr>
                <th></th>
                <th>Reference</th>
                <th>Year</th>
                <th>Source DB</th>
                <th>Used in</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={c.key}>
                  <td className="row-num">{String(i + 1).padStart(2, "0")}</td>
                  <td>
                    <div style={{ fontFamily: "var(--font-serif)", fontSize: 14.5, fontWeight: 600, color: "var(--ink-900)", lineHeight: 1.3 }}>
                      {c.title}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-500)", marginTop: 4 }}>{c.authors}</div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-400)", marginTop: 2, fontStyle: "italic" }}>
                      {c.venue} · <span style={{ fontFamily: "var(--font-mono)" }}>{c.doi}</span>
                    </div>
                  </td>
                  <td style={{ fontWeight: 700 }}>{c.year}</td>
                  <td>
                    <span style={{
                      fontSize: 11, fontWeight: 800, letterSpacing: "0.04em",
                      color: "var(--ok-fg)", background: "var(--ok-bg)",
                      padding: "3px 8px", borderRadius: 999,
                      display: "inline-flex", alignItems: "center", gap: 4,
                    }}>
                      <Icon name="check" size={10} stroke={3} /> {c.source}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: "var(--ink-500)" }}>
                    §{[1, 2.1, 2.3, 4.1, 4.2, 5][i % 6]} · {[2, 1, 3, 1, 2, 1][i % 6]}×
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="iconbtn" style={{ width: 32, height: 32 }}>
                        <Icon name="eye" size={14} />
                      </button>
                      <button className="iconbtn" style={{ width: 32, height: 32 }}>
                        <Icon name="swap" size={14} />
                      </button>
                      <button className="iconbtn" style={{ width: 32, height: 32 }}>
                        <Icon name="link" size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "flagged" && (
          <div style={{ padding: "24px" }}>
            <ConflictRow
              title="Brundage, M., Avin, S., Wang, J., et al. (2020). Toward Trustworthy AI Development."
              issue="Two papers with similar titles in CrossRef and arXiv — Verifier wants a human call."
              a={{ src: "CrossRef", doi: "10.1145/3442188.3445922", year: 2020 }}
              b={{ src: "arXiv",    doi: "2004.07213",            year: 2020 }}
            />
            <hr className="hr" style={{ margin: "20px 0" }} />
            <ConflictRow
              title="Calo, R. (2017). Artificial Intelligence Policy: A Primer and Roadmap."
              issue="Publication year mismatch — CrossRef shows 2017 (UC Davis Law), Semantic Scholar shows 2018 (preprint). Using earlier."
              a={{ src: "CrossRef", doi: "10.2139/ssrn.3015350", year: 2017 }}
              b={{ src: "Semantic Scholar", doi: "10.2139/ssrn.3015350", year: 2018 }}
            />
          </div>
        )}

        {tab === "rejected" && (
          <div style={{ padding: "24px" }}>
            {REJECTED.map((r, i) => (
              <RejectedRow key={i} {...r} />
            ))}
          </div>
        )}

        {tab === "queued" && (
          <div style={{ padding: "24px", color: "var(--ink-500)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Icon name="hourglass" size={16} stroke={2} style={{ color: "var(--blue-600)" }} />
              <b style={{ color: "var(--ink-900)" }}>Scout is verifying 6 new candidate sources…</b>
            </div>
            <div style={{ fontSize: 13 }}>
              These were discovered by Signal during gap analysis. Verifier is currently checking each
              against CrossRef and OpenAlex. You&apos;ll be notified if any can&apos;t be confirmed.
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

const SourcePill = ({ source, n, accent }) => (
  <div style={{
    background: "var(--paper)",
    border: "1px solid var(--ink-100)",
    borderRadius: 14, padding: "14px 18px",
    display: "flex", alignItems: "center", gap: 14,
  }}>
    <div style={{
      width: 38, height: 38, borderRadius: 10,
      background: `${accent}18`, color: accent,
      display: "grid", placeItems: "center",
    }}>
      <Icon name="library" size={18} />
    </div>
    <div>
      <div style={{ fontSize: 11, color: "var(--ink-400)", textTransform: "uppercase",
                    letterSpacing: "0.08em", fontWeight: 700 }}>Source</div>
      <div style={{ fontSize: 15, fontWeight: 800, color: "var(--ink-900)" }}>
        {source} <span style={{ color: accent, marginLeft: 4 }}>{n}</span>
      </div>
    </div>
  </div>
);

const ConflictRow = ({ title, issue, a, b }) => (
  <div>
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10,
        background: "var(--pause-bg)", color: "var(--pause-fg)",
        display: "grid", placeItems: "center", flexShrink: 0,
      }}>
        <Icon name="warning" size={18} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 16, fontWeight: 600, color: "var(--ink-900)" }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 6, lineHeight: 1.5 }}>
          {issue}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
          <CandidateCard {...a} preferred />
          <CandidateCard {...b} />
        </div>
      </div>
    </div>
  </div>
);

const CandidateCard = ({ src, doi, year, preferred }) => (
  <div style={{
    border: `1.5px solid ${preferred ? "var(--blue-600)" : "var(--ink-200)"}`,
    borderRadius: 12, padding: 14,
    background: preferred ? "var(--blue-50)" : "var(--paper)",
    position: "relative",
  }}>
    {preferred && (
      <span style={{
        position: "absolute", top: -10, right: 12,
        background: "var(--blue-600)", color: "white",
        fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 999,
        letterSpacing: 0.4,
      }}>PREFERRED</span>
    )}
    <div style={{ fontSize: 11, color: "var(--ink-400)", textTransform: "uppercase",
                  letterSpacing: "0.08em", fontWeight: 700 }}>Source</div>
    <div style={{ fontSize: 14, fontWeight: 800, marginTop: 2, color: "var(--ink-900)" }}>{src}</div>
    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-500)", marginTop: 6 }}>{doi}</div>
    <div style={{ fontSize: 13, color: "var(--ink-700)", marginTop: 6 }}>Published {year}</div>
    <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
      <button className="btn btn-sm btn-secondary" style={{ flex: 1 }}>Use this</button>
      <button className="btn btn-sm btn-ghost"><Icon name="link" size={12}/></button>
    </div>
  </div>
);

const RejectedRow = ({ title, reason, by }) => (
  <div style={{ display: "flex", gap: 14, padding: "14px 0", borderBottom: "1px solid var(--ink-100)" }}>
    <div style={{
      width: 32, height: 32, borderRadius: 10,
      background: "var(--stop-bg)", color: "var(--stop-fg)",
      display: "grid", placeItems: "center", flexShrink: 0,
    }}>
      <Icon name="warning" size={16} />
    </div>
    <div style={{ flex: 1 }}>
      <div style={{ fontFamily: "var(--font-serif)", fontSize: 14.5, fontWeight: 600, color: "var(--ink-700)", textDecoration: "line-through", textDecorationColor: "var(--ink-300)" }}>
        {title}
      </div>
      <div style={{ fontSize: 12.5, color: "var(--ink-500)", marginTop: 4 }}>{reason}</div>
      <div style={{ fontSize: 11, color: "var(--ink-400)", marginTop: 4, fontWeight: 600 }}>Rejected by {by}</div>
    </div>
    <button className="btn btn-ghost btn-sm">Restore</button>
  </div>
);
