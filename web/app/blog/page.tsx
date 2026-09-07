import { redirect } from "next/navigation";

import { DEFAULT_LOCALE } from "../lib/i18n/locale";
import { blogPath } from "./_lib/site";

/**
 * `/blog` has no content of its own — every post lives under a locale.
 *
 * A permanent redirect rather than rendering the Vietnamese listing here:
 * two URLs serving the same list is the duplicate-content problem the
 * canonical tag exists to clean up, and a 308 avoids creating it at all.
 */
export default function BlogRootPage(): never {
  redirect(blogPath(DEFAULT_LOCALE));
}
