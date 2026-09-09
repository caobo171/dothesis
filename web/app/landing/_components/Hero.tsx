/** Hero + trust strip + university wordmarks.

    The idea→thesis demo it wraps now lives in ./ProductMock — it was 780 of
    this file's 970 lines, and the auth screens render it too. */
"use client";

import { Button } from "./ds";
import { ProductMock } from "./ProductMock";
import { CTA_HREF, CTA_PRIMARY, IconArrow } from "./shared";

function TrustRow() {
  const people: Array<[string, string]> = [
    ["MN", "#1c2eff"],
    ["TP", "#4a6b4f"],
    ["HL", "#8e6b2a"],
    ["QD", "#27272a"],
    ["AV", "#5b3aa8"],
  ];
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 14,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex" }} aria-hidden="true">
        {people.map(([initials, color], i) => (
          <span
            key={initials}
            style={{
              width: 34,
              height: 34,
              borderRadius: 999,
              background: color,
              color: "#fff",
              fontSize: 12,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "2px solid #fff",
              marginLeft: i ? -10 : 0,
            }}
          >
            {initials}
          </span>
        ))}
      </div>
      <p style={{ fontSize: 14, color: "var(--ink-500)", lineHeight: 1.4 }}>
        <strong style={{ color: "var(--ink-800)" }}>
          Trusted by graduate students
        </strong>{" "}
        at 40+ universities
      </p>
    </div>
  );
}

export function Hero() {
  return (
    <section
      id="top"
      style={{
        background:
          "linear-gradient(to bottom, rgba(238,242,255,0.6), #fff)",
        borderBottom: "1px solid var(--ink-100)",
      }}
    >
      <div
        className="lp-wrap"
        style={{ padding: "44px 28px 0", textAlign: "center" }}
      >
        {/* Removed the "19 specialized agents" eyebrow pill — that count is no
            longer accurate, and the claim isn't load-bearing for the hero. */}
        <h1
          className="lp-display"
          style={{
            // jenni hero H1: Inter Medium, 62px desktop → ~46px small, with the
            // very tight -2.3px (≈ -0.037em) tracking and 1.05 line-height that
            // define its look. Em-based tracking so it scales with the clamp.
            fontSize: "clamp(40px,6vw,62px)",
            letterSpacing: "-0.037em",
            lineHeight: 1.05,
            maxWidth: 720,
            margin: "0 auto",
          }}
        >
          From a topic idea to a submitted thesis.
        </h1>
        <p
          className="lp-lead"
          style={{
            marginTop: 16,
            fontSize: 16.5,
            maxWidth: 440,
            marginInline: "auto",
          }}
        >
          One thread. Real sources. Every citation traced.
        </p>
        <div
          style={{
            display: "flex",
            gap: 12,
            marginTop: 26,
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          <Button
            as="a"
            href={CTA_HREF}
            pill
            size="lg"
            iconAfter={<IconArrow />}
          >
            {/* one expression, not `{CTA_PRIMARY} — …`: JSX trims the leading
                space off the following text node and the dash jams into the
                label ("Start your thesis— it's free") */}
            {`${CTA_PRIMARY} — it's free`}
          </Button>
          <Button as="a" href="#features" pill size="lg" variant="secondary">
            See how it works
          </Button>
        </div>
        <div style={{ marginTop: 26 }}>
          <TrustRow />
        </div>
        <div style={{ maxWidth: 980, margin: "36px auto 0" }}>
          <ProductMock />
        </div>
      </div>
      <div style={{ height: 56 }} />
    </section>
  );
}

/** University wordmark strip — text wordmarks, no fake logos. */
export function LogoStrip() {
  const unis = [
    "VNU Hanoi",
    "HUST",
    "RMIT Vietnam",
    "NUS",
    "University of Melbourne",
    "TU Delft",
  ];
  return (
    <section
      style={{
        padding: "44px 0",
        borderBottom: "1px solid var(--ink-100)",
        background: "#fff",
      }}
    >
      <div className="lp-wrap">
        <p
          className="lp-eyebrow"
          style={{ textAlign: "center", marginBottom: 26 }}
        >
          Theses drafted by students at
        </p>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            alignItems: "center",
            gap: "26px 48px",
          }}
        >
          {unis.map((u) => (
            <span
              key={u}
              className="lp-serif"
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: "var(--ink-300)",
                letterSpacing: "-0.01em",
              }}
            >
              {u}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
