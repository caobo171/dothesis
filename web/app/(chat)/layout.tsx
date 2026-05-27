"use client";

import type { ReactNode } from "react";
import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import { useSidebarSections } from "@/app/components/layout/use-sections";


export default function ChatRouteLayout({ children }: { children: ReactNode }) {
  const sections = useSidebarSections();
  // fullBleed: chat owns its own pane layout + viewport-height math. The
  // shell's default py-10 + max-w-7xl + gradient backdrop would carve the
  // chat into a centered column with empty space above the threads list.
  return (
    <SidebarLayout sections={sections} fullBleed>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
