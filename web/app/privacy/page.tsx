import { redirect } from "next/navigation";

import { DEFAULT_LOCALE } from "../lib/i18n/locale";
import { legalPath } from "../legal/_lib/site";

/**
 * `/privacy` has no edition of its own — the policy lives under a locale.
 *
 * Same rule as `/blog`: a 308 rather than rendering the Vietnamese edition here,
 * because two URLs serving identical text is the duplicate-content problem the
 * canonical tag exists to clean up, and redirecting avoids creating it at all.
 *
 * It matters more here than on the blog: `/privacy` is the bare path a payment
 * provider, an app store or a browser extension review will be given, so it has
 * to resolve rather than 404.
 */
export default function PrivacyRootPage(): never {
  redirect(legalPath("privacy", DEFAULT_LOCALE));
}
