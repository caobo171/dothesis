import { NextResponse } from "next/server";

const PUBLIC_PATHS = [
  "/login", "/signup",
  "/verify", "/wait-verify",
  "/forgot-password", "/reset-password",
  "/_next", "/favicon.ico",
];

export function proxy(request) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookie = request.cookies.get("opendraft_session");
  if (!cookie) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
