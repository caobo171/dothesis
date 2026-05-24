"use client";

import type { ReactNode } from "react";

import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import { useSidebarSections } from "@/app/components/layout/use-sections";

export default function InAppLayout({ children }: { children: ReactNode }) {
  const sections = useSidebarSections();
  return (
    <SidebarLayout sections={sections}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
