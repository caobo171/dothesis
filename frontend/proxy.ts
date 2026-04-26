import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const authPages = ['/login', '/register', '/wait-verify', '/verify'];
const protectedPrefixes = ['/humanizer', '/auto-cite', '/library', '/history'];

async function verifyUser(accessToken: string) {
  try {
    const res = await fetch(`${API_URL}/api/me`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.code === 1 ? data.data : null;
  } catch {
    return null;
  }
}

export default async function proxy(req: NextRequest) {
  const path = req.nextUrl.pathname;
  const accessToken = req.cookies.get('access_token')?.value;

  // Root → redirect to login
  if (path === '/') {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  // Auth pages: if user is valid, redirect to workspace
  if (authPages.some((p) => path.startsWith(p))) {
    if (accessToken) {
      const user = await verifyUser(accessToken);
      if (user) {
        return NextResponse.redirect(new URL('/humanizer', req.url));
      }
    }
    return NextResponse.next();
  }

  // Protected pages: verify user with backend
  if (protectedPrefixes.some((p) => path.startsWith(p))) {
    if (!accessToken) {
      return NextResponse.redirect(new URL('/login', req.url));
    }

    const user = await verifyUser(accessToken);
    if (!user) {
      return NextResponse.redirect(new URL('/login', req.url));
    }

    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
