/**
 * Page chrome for every blog route.
 *
 * Reuses the landing page's Nav and Footer inside its `.lp-root` scope so the
 * blog is visibly the same product as the marketing site. The alternative —
 * a blog-only header — would have been faster and would have made the one
 * surface Google sends strangers to look like somebody else's website.
 *
 * Importing landing.css here rather than in each route keeps the token scope
 * and the `.lp-root` wrapper in the same file: they only work together.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import "../../landing/landing.css";
import "../blog.css";

import { Footer } from "../../landing/_components/Footer";
import { Nav } from "../../landing/_components/Nav";
import { DEFAULT_LOCALE, isLocale } from "../../lib/i18n/locale";
import { HREFLANG, LANGUAGE_NAME, otherLocale } from "../_lib/hreflang";
import { blogPath } from "../_lib/site";

/**
 * The blog shell, with the switch between language editions.
 *
 * A reader on a Vietnamese post had no way to reach the English blog at all —
 * the Nav is shared with the marketing site and points at one hardcoded
 * listing. The switch lives here rather than in each page so every blog route
 * gets it without deciding anything.
 *
 * `alternate` is the counterpart page when the caller has *verified* one (the
 * category hub does, through `pairedCategoryPath`). Left out, the switch goes
 * to the other edition's blog root: a reader who wanted English and lands on
 * the English listing has been helped, while a guessed slug would have handed
 * them a 404. Same rule the hreflang annotation follows, for the same reason.
 *
 * The label is written in the language it leads to — a reader looking for
 * Vietnamese is scanning for "Tiếng Việt", not for "Vietnamese" — and carries
 * `lang`/`hrefLang` so a screen reader switches voice on it and a crawler reads
 * it as an edition link rather than as navigation.
 */
export function BlogShell({
  locale,
  alternate,
  children,
}: {
  locale: string;
  alternate?: string;
  children: ReactNode;
}) {
  const other = otherLocale(isLocale(locale) ? locale : DEFAULT_LOCALE);
  return (
    <div className="lp-root">
      <Nav />
      <main className="blog-page">
        <div className="lp-wrap">
          <div className="blog-langbar">
            <Link
              className="blog-langswitch"
              href={alternate ?? blogPath(other)}
              hrefLang={HREFLANG[other]}
              lang={HREFLANG[other]}
              rel="alternate"
            >
              {LANGUAGE_NAME[other]}
            </Link>
          </div>
        </div>
        {children}
      </main>
      <Footer />
    </div>
  );
}
