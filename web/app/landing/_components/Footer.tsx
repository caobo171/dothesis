import { BrandLockup } from "./shared";

// `shared.tsx` is a client module because BrandLockup animates; importing a
// scalar from it into this server component produces a client reference rather
// than a URL. Keep this build-time routing constant server-local.
const LANDING_HREF = process.env.NEXT_PUBLIC_MARKETING_HOST ? "/" : "/landing";

/**
 * The design ships every footer link as `href="#"`. Where a real destination
 * exists it is wired up; About and Careers stay as placeholders because those
 * pages do not exist yet — inventing routes here would just move the dead link
 * somewhere harder to notice.
 *
 * Legal and Contact stopped being placeholders when `app/{privacy,terms,
 * contact}` landed. That matters beyond tidiness: these are the URLs a payment
 * provider's review asks for, and `#` is not an answer to "where are your
 * terms".
 *
 * `Refunds` points at the Terms, where the refund rules actually are, rather
 * than at a page of its own. One statement of when a run is refunded is easier
 * to keep true than two.
 */
function columns(locale?: string): Array<[string, Array<[string, string]>]> {
  // Bare `/privacy` 308s to the default edition. Passing a locale skips that
  // hop AND keeps the reader in the language they were already reading — a
  // reader on the English blog should not be bounced to Vietnamese terms.
  const l = locale ? `/${locale}` : "";
  return [
    [
      "Product",
      [
        ["Features", `${LANDING_HREF}#features`],
        ["Tools", `${LANDING_HREF}#tools`],
        ["Pricing", `${LANDING_HREF}#pricing`],
      ],
    ],
    [
      "Compare",
      [
        ["vs ThesisAI", "/compare/thesisai"],
        ["vs Jenni AI", "/compare/jenni-ai"],
        ["vs Paperguide", "/compare/paperguide"],
        ["All comparisons", "/compare"],
      ],
    ],
    [
      "Company",
      [
        ["About", "#"],
        ["Blog", `/blog/${locale ?? "vi"}`],
        ["Careers", "#"],
        ["Contact", `/contact${l}`],
      ],
    ],
    [
      "Legal",
      [
        ["Terms", `/terms${l}`],
        ["Privacy", `/privacy${l}`],
        ["Refunds", `/terms${l}`],
      ],
    ],
  ];
}

export function Footer({ locale }: { locale?: string } = {}) {
  const COLUMNS = columns(locale);
  return <FooterBody columns={COLUMNS} />;
}

function FooterBody({ columns: COLUMNS }: { columns: ReturnType<typeof columns> }) {
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
          <span>
            © 2026{" "}
            <a
              href="https://hiesolution.com"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "rgba(255,255,255,0.6)" }}
            >
              HIE Solution
            </a>
            . All rights reserved.
          </span>
          <span>English · Tiếng Việt</span>
        </div>
      </div>
    </footer>
  );
}
