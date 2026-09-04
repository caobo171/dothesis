"use client";

// The root route is the app's real landing page. 2026-09 — replaced the
// greeting/stats/theses DASHBOARD with a straight-to-the-point, prompt-first
// launcher (the /new start flow lifted onto `/`). The full theses list lives at
// /papers in the sidebar; HomeLauncher keeps a single "continue where you left
// off" strip for the most recent one.
import { HomeLauncher } from "@/app/components/chat/HomeLauncher";

export default function Page() {
  return <HomeLauncher />;
}
