/**
 * Display formatting for the blog's meta lines.
 *
 * The timezone is pinned rather than left to the runtime. These strings are
 * rendered on the server and shipped as static HTML, so an unpinned formatter
 * would print whatever timezone the container happens to run in — and a post
 * published at 00:30 Hanoi time would read as the previous day to every
 * reader. Vietnamese posts are dated in the readership's own timezone; other
 * locales get UTC, which is what the API stores.
 */
const TIME_ZONE: Record<string, string> = { vi: "Asia/Ho_Chi_Minh" };

const INTL_LOCALE: Record<string, string> = { vi: "vi-VN", en: "en-US" };

/** "1 tháng 9, 2026" / "September 1, 2026". Empty string for a missing date. */
export function formatDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(INTL_LOCALE[locale] ?? "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: TIME_ZONE[locale] ?? "UTC",
  }).format(d);
}

/** "9 phút đọc" / "9 min read". */
export function formatReadingTime(minutes: number | null | undefined, locale: string): string {
  if (!minutes || minutes < 1) return "";
  return locale === "vi" ? `${minutes} phút đọc` : `${minutes} min read`;
}
