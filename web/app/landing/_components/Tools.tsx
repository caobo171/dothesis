/** Standalone tools — each card states plainly what the tool cannot do. */
import { Badge, Card, Caveat } from "./ds";
import { Reveal, SectionHead } from "./shared";

const TOOLS: Array<[string, string, string, string]> = [
  [
    "Humanize",
    "Make drafted prose read as human-written",
    "Re-voice prose so it stops reading as AI — without changing what it says.",
    "A rewrite that would change any number or citation is discarded. No claim about detector scores.",
  ],
  [
    "Writing rhythm",
    "Measure how mechanical your sentences are",
    "Sentence-length variation and connector density — supervisor-style feedback.",
    "This is not an AI detector. It does not predict Turnitin, and a low number is not a pass.",
  ],
  [
    "Citation generator",
    "Cite what isn't, verify what is",
    "Rebuild your reference list from CrossRef and source uncited claims.",
    "A fuzzy hit is evidence, not proof. Check titles and authors against what you cited.",
  ],
  [
    "Similarity & citations",
    "A self-check over your own file",
    "See what repeats and whether quotations and references agree.",
    "It searches no web index, so it is not a similarity percentage or a Turnitin score.",
  ],
];

export function Tools() {
  return (
    <section id="tools" className="lp-sec">
      <div className="lp-wrap">
        <SectionHead
          eyebrow="Standalone tools"
          title="One job, one answer."
          sub="Run a single job on its own — each tool says plainly what it can, and cannot, do."
        />
        <div
          className="lp-tool-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            marginTop: 48,
          }}
        >
          {TOOLS.map(([name, tagline, body, caveat], i) => {
            // The caveat's first sentence is the bolded lead; the rest is the
            // qualifier that follows it.
            const split = caveat.indexOf(".");
            return (
              <Reveal key={name} delay={i * 60}>
                <Card
                  panel
                  interactive
                  style={{
                    padding: 26,
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 10,
                    }}
                  >
                    <h3
                      style={{
                        fontSize: 17,
                        fontWeight: 700,
                        color: "var(--ink-900)",
                      }}
                    >
                      {name}
                    </h3>
                    <Badge tone="idle">Tool</Badge>
                  </div>
                  <div
                    style={{
                      fontSize: 13.5,
                      fontWeight: 600,
                      color: "var(--primary-700)",
                    }}
                  >
                    {tagline}
                  </div>
                  <p
                    style={{
                      fontSize: 14,
                      color: "var(--ink-500)",
                      lineHeight: 1.6,
                    }}
                  >
                    {body}
                  </p>
                  <div style={{ marginTop: "auto", paddingTop: 6 }}>
                    <Caveat lead={`${caveat.slice(0, split)}.`}>
                      {caveat.slice(split + 1)}
                    </Caveat>
                  </div>
                </Card>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
