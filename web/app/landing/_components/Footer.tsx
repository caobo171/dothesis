import { BrandLockup } from "./shared";

/**
 * The design ships every footer link as `href="#"`. Where a real destination
 * already exists on this page it is wired up; Company and Legal stay as
 * placeholders because those pages do not exist yet — inventing routes here
 * would just move the dead link somewhere harder to notice.
 */
const COLUMNS: Array<[string, Array<[string, string]>]> = [
  [
    "Product",
    [
      ["Features", "#features"],
      ["Tools", "#tools"],
      ["Pricing", "#pricing"],
    ],
  ],
  [
    "Tools",
    [
      ["Humanize", "#tools"],
      ["Writing rhythm", "#tools"],
      ["Citation generator", "#tools"],
      ["Similarity & citations", "#tools"],
    ],
  ],
  [
    "Company",
    [
      ["About", "#"],
      ["Blog", "#"],
      ["Careers", "#"],
      ["Contact", "#"],
    ],
  ],
  [
    "Legal",
    [
      ["Terms", "#"],
      ["Privacy", "#"],
      ["Refunds", "#"],
    ],
  ],
];

export function Footer() {
  return (
    <footer
      className="lp-footer"
      style={{
        background: "var(--ink-900)",
        borderTop: "1px solid rgba(255,255,255,0.08)",
        color: "rgba(255,255,255,0.6)",
      }}
    >
      <div className="lp-wrap" style={{ padding: "56px 28px 40px" }}>
        <div
          className="lp-foot-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr repeat(4,1fr)",
            gap: 32,
          }}
        >
          <div>
            <BrandLockup light />
            <p
              style={{
                fontSize: 13.5,
                marginTop: 16,
                maxWidth: 240,
                lineHeight: 1.55,
              }}
            >
              Draft with conviction. An AI thesis agent for graduate students.
            </p>
          </div>
          {COLUMNS.map(([title, links]) => (
            <div key={title}>
              <div
                className="lp-eyebrow"
                style={{ color: "rgba(255,255,255,0.4)", marginBottom: 16 }}
              >
                {title}
              </div>
              <ul
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 11,
                }}
              >
                {links.map(([label, href]) => (
                  <li key={label}>
                    <a
                      href={href}
                      style={{
                        color: "rgba(255,255,255,0.6)",
                        fontSize: 13.5,
                      }}
                    >
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 48,
            paddingTop: 24,
            borderTop: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
            fontSize: 12.5,
            color: "rgba(255,255,255,0.4)",
          }}
        >
          <span>© 2026 DoThesis. All rights reserved.</span>
          <span>English · Tiếng Việt</span>
        </div>
      </div>
    </footer>
  );
}
