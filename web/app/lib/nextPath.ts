/**
 * Where to send someone after they sign in.
 *
 * Two things this fixes, both surfaced by the MCP connector work:
 *
 * 1. NOT EVERY DESTINATION IS A NEXT ROUTE. `/oauth/authorize` is served by the
 *    MCP process — nginx routes it there before Next ever sees it (see
 *    deploy/nginx/dothesis.conf). `router.push()` would try to client-route to
 *    a segment the App Router doesn't have and render the 404 page, stranding
 *    the user mid-OAuth. A real navigation is the only thing that works for an
 *    arbitrary same-origin path, and it costs one page load on a transition
 *    that already re-bootstraps auth state anyway.
 *
 * 2. `next` IS ATTACKER-CONTROLLED. It comes straight off the query string, so
 *    `?next=https://evil.example` turned the login page into an open redirect
 *    that renders on our domain — a credible phishing hop. Only same-origin
 *    absolute paths are allowed through now.
 */

/** Reduce a raw `?next=` value to a safe same-origin path, or "/" if it isn't one. */
export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return "/";
  // Must be an absolute path on THIS origin. "//evil.example" is a
  // protocol-relative URL and navigates off-site despite the leading slash;
  // "/\evil.example" is the same trick, since browsers fold "\" to "/".
  if (!raw.startsWith("/")) return "/";
  if (raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  return raw;
}

/** Navigate to a post-login destination. Full page load — see the note above. */
export function goToNext(raw: string | null | undefined): void {
  if (typeof window === "undefined") return;
  window.location.assign(safeNextPath(raw));
}
