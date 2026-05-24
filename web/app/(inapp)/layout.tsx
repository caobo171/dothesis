"use client";

import {
  CurrencyDollarIcon,
  DocumentTextIcon,
  HomeIcon,
  PlusIcon,
} from "@heroicons/react/24/outline";
import type { ReactNode } from "react";

import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import type { SidebarSection } from "@/app/components/layout/sections";

const SECTIONS: SidebarSection[] = [
  {
    id: "workspace",
    name: "Workspace",
    options: [
      { name: "Dashboard", href: "/", icon: HomeIcon, default: true },
      { name: "New Thesis", href: "/wizard", icon: PlusIcon },
      { name: "Drafts", href: "/papers", icon: DocumentTextIcon },
    ],
  },
  {
    id: "account",
    name: "Account",
    options: [{ name: "Credit", href: "/credit", icon: CurrencyDollarIcon }],
  },
];

export default function InAppLayout({ children }: { children: ReactNode }) {
  return (
    <SidebarLayout sections={SECTIONS}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
