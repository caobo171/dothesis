/**
 * Page chrome for the legal and contact routes.
 *
 * Same decision as `BlogShell`, for the same reason: these pages reuse the
 * landing Nav and Footer inside `.lp-root` so the one surface a reader checks
 * before trusting us with a payment looks like the product they were just on,
 * rather than like a bolted-on document host.
 *
 * The language switch is here rather than in each page because, unlike the
 * blog, both editions of a legal document ALWAYS exist — they ship in the same
 * file — so the counterpart never has to be verified and never 404s.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import "../../landing/landing.css";
import "../../blog/blog.css";

import { Footer } from "../../landing/_components/Footer";
import { Nav } from "../../landing/_components/Nav";
import { HREFLANG, LANGUAGE_NAME, otherLocale } from "../../blog/_lib/hreflang";
import { type Locale } from "../../lib/i18n/locale";
import { type LegalDoc, legalPath } from "../_lib/site";

export function LegalShell({
  doc,
  locale,
  title,
  meta,
  children,
}: {
  doc: LegalDoc;
  locale: Locale;
  title: string;
  /** The "last updated" line. Omitted on Contact, which has no effective date. */
  meta?: string;
  children: ReactNode;
}) {
  const other = otherLocale(locale);
  return (
    <div className="lp-root">
      <Nav />
      <main className="blog-page">
        <div className="lp-wrap">
          <div className="blog-measure blog-langbar">
            <Link
              className="blog-langswitch"
              href={legalPath(doc, other)}
              hrefLang={HREFLANG[other]}
              lang={HREFLANG[other]}
              rel="alternate"
            >
              {LANGUAGE_NAME[other]}
            </Link>
          </div>
          <div className="blog-measure">
            <h1 className="blog-hero__title" style={{ marginTop: 18 }}>
              {title}
            </h1>
            {meta ? (
              <div className="lp-eyebrow" style={{ marginTop: 14 }}>
                {meta}
              </div>
            ) : null}
            {/* `blog-prose` rather than a legal-only stylesheet: the type ramp,
                the list indents and the link treatment are already decided for
                long-form reading on this site, and a second prose class would
                drift from the first the moment either is retuned. */}
            <div className="blog-prose" style={{ marginTop: 34 }}>
              {children}
            </div>
          </div>
        </div>
      </main>
      <Footer locale={locale} />
    </div>
  );
}
