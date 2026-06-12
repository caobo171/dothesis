"use client";

import type { ReactNode } from "react";
import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";

/**
 * Chat surface — no master menu.
 *
 * History: this layout used to wrap children in <SidebarLayout> with the
 * global Dashboard / Theses / Credit nav. Design feedback was that once
 * you're inside a thesis, the workflow rails (M1–M5) + context store live
 * in their own project-specific panes (ChatShellLayout's leftPane and
 * rightPane), and the global nav is just noise. Stripping the shell here
 * also reclaims ~250px of horizontal space the master menu was eating.
 *
 * AnnouncementProvider is kept because announcements are surfaced via a
 * floating banner inside the chat, not the master menu.
 */
export default function ChatRouteLayout({ children }: { children: ReactNode }) {
  return (
    <AnnouncementProvider>
      <div className="h-screen w-screen overflow-hidden bg-white">{children}</div>
    </AnnouncementProvider>
  );
}
