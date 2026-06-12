"use client";

// 2026-06-10 — the root route is the app's real landing page, so the new
// Home.html design dashboard lives here (not at /chat, which nothing in the
// sidebar nav linked to). Replaces the legacy drafts Dashboard; the drafts
// list itself is still reachable at /papers.
import { HomeDashboard } from "@/app/components/chat/HomeDashboard";

export default function Page() {
  return <HomeDashboard />;
}
