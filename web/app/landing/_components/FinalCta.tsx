/** Closing CTA on the dark block, with the three headline numbers. */
import { Button } from "./ds";
import { CTA_HREF, CTA_PRIMARY, IconArrow } from "./shared";

const STATS: Array<[string, string]> = [
  // Was "19 specialized agents" — that count is no longer accurate. The lead
  // promise is the flagship instead: one prompt to a full thesis.
  ["1", "prompt to a full thesis"],
  ["5", "modules, one thread"],
  ["100%", "citations verified"],
];

export function FinalCta() {
  return (
    <section
      id="start"
      style={{
        background: "var(--ink-900)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <svg
        viewBox="0 0 1200 600"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          opacity: 0.07,
        }}
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <circle
            key={i}
            cx="600"
            cy="300"
            r={80 + i * 90}
            fill="none"
            stroke="#fff"
            strokeWidth="1"
          />
        ))}
      </svg>
      <div
        className="lp-wrap"
        style={{
          position: "relative",
          padding: "108px 28px",
          textAlign: "center",
        }}
      >
        <h2
          className="lp-display"
          style={{ fontSize: "clamp(32px,4vw,48px)", color: "#fff" }}
        >
          Start your thesis today.
        </h2>
        <p
          className="lp-lead"
          style={{
            color: "rgba(255,255,255,0.68)",
            marginTop: 20,
            maxWidth: 560,
            marginInline: "auto",
          }}
        >
          Draft with conviction — one thread, your sources, page-cited. Never
          look back at the blank page.
        </p>
        <div style={{ marginTop: 34 }}>
          <Button
            as="a"
            href={CTA_HREF}
            pill
            size="lg"
            iconAfter={<IconArrow />}
          >
            {CTA_PRIMARY}
          </Button>
        </div>
        <p
          style={{
            marginTop: 16,
            fontSize: 13,
            color: "rgba(255,255,255,0.45)",
          }}
        >
          Free credits to start · no card required · cancel anytime
        </p>
        {/* the nav's "Pricing" link lands here — credits are the pricing story */}
        <div
          id="pricing"
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 56,
            marginTop: 68,
            flexWrap: "wrap",
          }}
        >
          {STATS.map(([value, label]) => (
            <div key={label}>
              <div
                className="lp-serif lp-tnum"
                style={{
                  fontSize: 40,
                  fontWeight: 800,
                  color: "#fff",
                  letterSpacing: "-0.02em",
                }}
              >
                {value}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: "rgba(255,255,255,0.6)",
                  marginTop: 6,
                }}
              >
                {label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
