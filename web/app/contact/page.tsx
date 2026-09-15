import { redirect } from "next/navigation";

import { DEFAULT_LOCALE } from "../lib/i18n/locale";
import { legalPath } from "../legal/_lib/site";

/** See `app/privacy/page.tsx` — same redirect, same reason. */
export default function ContactRootPage(): never {
  redirect(legalPath("contact", DEFAULT_LOCALE));
}
