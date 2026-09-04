/** What students tell their supervisors. */
import { Card } from "./ds";
import { Reveal, SectionHead } from "./shared";

const QUOTES: Array<[string, string, string, string, string]> = [
  [
    "No waiting for feedback anymore — direct support at any point in the writing process. It takes a real burden off my supervisor.",
    "Minh N.",
    "PhD candidate, Transport Planning",
    "MN",
    "#1c2eff",
  ],
  [
    "I stopped fighting a blank chat box. The module structure meant I always knew what came next, and the citations actually checked out.",
    "Thu P.",
    "MSc, Public Policy",
    "TP",
    "#4a6b4f",
  ],
  [
    "My supervisor said my draft read like ChatGPT. Humanize fixed the voice without touching a single number in my results.",
    "Huy L.",
    "PhD candidate, Information Systems",
    "HL",
    "#8e6b2a",
  ],
];

export function Testimonials() {
  return (
    <section className="lp-sec" style={{ background: "var(--ink-50)" }}>
      <div className="lp-wrap">
        <SectionHead
          eyebrow="From the desk"
          title="What students tell their supervisors."
        />
        <div
          className="lp-quote-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3,1fr)",
            gap: 16,
            marginTop: 44,
          }}
        >
          {QUOTES.map(([quote, name, role, initials, color], i) => (
            <Reveal key={name} delay={i * 70}>
              <Card
                panel
                style={{
                  padding: 26,
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  gap: 20,
                }}
              >
                <p
                  className="lp-serif"
                  style={{
                    fontSize: 17,
                    lineHeight: 1.55,
                    color: "var(--ink-800)",
                    flex: 1,
                  }}
                >
                  “{quote}”
                </p>
                <div
                  style={{ display: "flex", alignItems: "center", gap: 12 }}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 999,
                      background: color,
                      color: "#fff",
                      fontSize: 13,
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {initials}
                  </span>
                  <div>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 700,
                        color: "var(--ink-900)",
                      }}
                    >
                      {name}
                    </div>
                    <div
                      style={{ fontSize: 12.5, color: "var(--ink-500)" }}
                    >
                      {role}
                    </div>
                  </div>
                </div>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
