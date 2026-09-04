/** Who it's for. */
import { SectionHead } from "./shared";

const CASES = [
  "Master's students",
  "PhD candidates",
  "Non-native English writers",
  "Supervisors & committees",
  "University research labs",
  "Anyone facing a blank page",
];

export function UseCases() {
  return (
    <section className="lp-sec">
      <div className="lp-wrap-narrow" style={{ textAlign: "center" }}>
        <SectionHead
          eyebrow="Who it's for"
          title="Wherever a thesis has to hold up."
          sub="DoThesis is bilingual — English and Tiếng Việt — and built first for graduate students who need cited, defensible writing."
        />
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 12,
            marginTop: 40,
          }}
        >
          {CASES.map((c) => (
            <span
              key={c}
              style={{
                fontSize: 14.5,
                fontWeight: 600,
                color: "var(--ink-700)",
                background: "#fff",
                border: "1px solid var(--ink-200)",
                borderRadius: 999,
                padding: "11px 20px",
              }}
            >
              {c}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
