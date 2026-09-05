/** DoThesis vs a general chatbot, side by side. */
import Image from "next/image";

import { Card } from "./ds";
import { IconCheck, IconX, LOGO, SectionHead } from "./shared";

// The right column describes a general chatbot as a CLASS — it names nobody,
// and it must stay that way. The moment a competitor is named, each of these
// lines becomes a factual assertion about that company rather than a
// characterisation of the category.
const ROWS: Array<[string, string]> = [
  [
    // Was "Draws only from the sources you upload" — the opposite of what M2
    // does. It searches Crossref, OpenAlex and Semantic Scholar; uploads are an
    // addition, not the whole pool.
    "Retrieves real papers from Crossref, OpenAlex and Semantic Scholar — plus any PDFs and DOIs you add",
    "Answers from general training data",
  ],
  [
    // Was "Every citation checked against CrossRef … never invented". Crossref
    // is one backend of several, a result is accepted on a DOI *or* a URL, and
    // the DOI existence check is off by default. What the code DOES guarantee
    // is the reference-pool check that runs on every composed chapter.
    "Citations checked against your project's reference list — anything not in it is stripped",
    "Citations formatted to look right, but unverified",
  ],
  [
    "Structured across five modules with a live context store",
    "One chat box, no structure carried between sessions",
  ],
  [
    "Humanize discards a rewrite that would change a number or a citation",
    "A rewrite can silently change a figure or a source",
  ],
  [
    "Metered in credits — you see the estimate before each run",
    "Flat subscription regardless of what you actually use",
  ],
];

export function Comparison() {
  return (
    <section className="lp-sec" style={{ background: "var(--ink-50)" }}>
      <div className="lp-wrap-narrow">
        <SectionHead eyebrow="Why DoThesis" title="Not another AI chatbot." />
        <div
          className="lp-cmp"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            marginTop: 44,
          }}
        >
          <Card
            panel
            style={{
              padding: 0,
              overflow: "hidden",
              border: "1.5px solid var(--primary-200,#c7cdff)",
            }}
          >
            <div
              style={{
                padding: "16px 22px",
                background: "var(--primary-50)",
                borderBottom: "1px solid var(--primary-100)",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <Image
                src={LOGO}
                width={22}
                height={22}
                style={{ borderRadius: 6 }}
                alt=""
              />
              <span
                className="lp-serif"
                style={{ fontWeight: 800, fontSize: 16 }}
              >
                DoThesis
              </span>
            </div>
            <ul style={{ padding: "8px 22px 20px" }}>
              {ROWS.map(([ours], i) => (
                <li
                  key={ours}
                  style={{
                    display: "flex",
                    gap: 12,
                    padding: "14px 0",
                    borderBottom:
                      i < ROWS.length - 1
                        ? "1px dashed var(--ink-200)"
                        : "none",
                  }}
                >
                  <span
                    style={{
                      color: "var(--moss-fg)",
                      flexShrink: 0,
                      marginTop: 1,
                    }}
                  >
                    <IconCheck />
                  </span>
                  <span
                    style={{
                      fontSize: 14,
                      color: "var(--ink-800)",
                      lineHeight: 1.5,
                    }}
                  >
                    {ours}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card panel style={{ padding: 0, overflow: "hidden" }}>
            <div
              style={{
                padding: "16px 22px",
                background: "var(--ink-100)",
                borderBottom: "1px solid var(--ink-200)",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 6,
                  background: "var(--ink-300)",
                }}
              />
              <span
                style={{
                  fontWeight: 700,
                  fontSize: 15,
                  color: "var(--ink-600)",
                }}
              >
                A general AI chatbot
              </span>
            </div>
            <ul style={{ padding: "8px 22px 20px" }}>
              {ROWS.map(([, theirs], i) => (
                <li
                  key={theirs}
                  style={{
                    display: "flex",
                    gap: 12,
                    padding: "14px 0",
                    borderBottom:
                      i < ROWS.length - 1
                        ? "1px dashed var(--ink-200)"
                        : "none",
                  }}
                >
                  <span
                    style={{
                      color: "var(--ink-400)",
                      flexShrink: 0,
                      marginTop: 1,
                    }}
                  >
                    <IconX />
                  </span>
                  <span
                    style={{
                      fontSize: 14,
                      color: "var(--ink-500)",
                      lineHeight: 1.5,
                    }}
                  >
                    {theirs}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </section>
  );
}
