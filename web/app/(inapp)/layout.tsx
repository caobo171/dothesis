"use client";

import {
  CurrencyDollarIcon,
  DocumentTextIcon,
  HomeIcon,
  PlusIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import { useMemo, type ReactNode } from "react";

import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import type { SidebarSection } from "@/app/components/layout/sections";
import { useMe } from "@/app/lib/use-me";

const BASE_SECTIONS: SidebarSection[] = [
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

const ADMIN_SECTION: SidebarSection = {
  id: "admin",
  name: "Admin",
  options: [{ name: "Admin Console", href: "/admin/users", icon: ShieldCheckIcon }],
};

export default function InAppLayout({ children }: { children: ReactNode }) {
  const me = useMe();
  const sections = useMemo<SidebarSection[]>(
    () => (me.data?.is_super_admin ? [...BASE_SECTIONS, ADMIN_SECTION] : BASE_SECTIONS),
    [me.data?.is_super_admin],
  );

  return (
    <SidebarLayout sections={sections}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
