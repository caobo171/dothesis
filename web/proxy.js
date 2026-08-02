import { NextResponse } from "next/server";

// Route gating happens server-side in this middleware. With JWT auth, the
// real authoritative token lives in localStorage — which the middleware
// CAN'T read (it runs on the edge runtime, no DOM). To keep the no-flash
// redirect behavior we used to get from the dothesis_session cookie, the
// client mirrors the token presence as a non-HTTPOnly cookie
// (`dothesis_access_token`, set by web/app/lib/tokenStore.ts). We check
// only that the cookie EXISTS — its value isn't validated here. If the
// token is expired or forged, the actual API will 401 and the client wipes
// both stores. The cookie is a hint for routing, not an auth statement.
const PUBLIC_PATHS = [
  "/login", "/signup",
  "/verify", "/wait-verify",
  "/forgot-password", "/reset-password",
  "/_next", "/favicon.ico",
];

const AUTH_MARKER_COOKIE = "dothesis_access_token";

// Files served straight out of web/public. The matcher below only spares
// `_next/*` and `favicon.ico`, so anything else in public/ (the logo mark, the
// actual favicon.png) was being 307'd to /login and rendering as a broken image
// on the signed-out auth screens — the one audience guaranteed to see them.
const PUBLIC_FILE = /\.(png|jpe?g|gif|svg|webp|avif|ico|woff2?|txt|xml|json)$/i;

export function proxy(request) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_FILE.test(pathname)) return NextResponse.next();
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const marker = request.cookies.get(AUTH_MARKER_COOKIE);
  if (!marker || !marker.value) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Exclude `api` — those requests are the Next-config rewrite proxy to the
  // FastAPI backend (fetch("/api/v1/...")). The API does its own JWT auth and
  // answers with 401 JSON; gating it here would 307-redirect the browser's
  // API calls (including the public POST /api/v1/auth/login) to the /login
  // PAGE, which breaks sign-in. Never route-gate the API through page middleware.
  // `mcp` and `.well-known` are excluded for the SAME reason as `api`, and it
  // is the same bug: they are machine endpoints, not pages. Gating them here
  // 307-redirected Claude's connector to the /login PAGE — it then failed OAuth
  // discovery (also redirected) and reported "Couldn't register with dothesis's
  // sign-in service". MCP does its own auth; page middleware must never see it.
  matcher: ["/((?!api|mcp(?:/|$)|\\.well-known/|_next/static|_next/image|favicon.ico).*)"],
};
