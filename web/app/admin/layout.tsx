"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import { useSidebarSections } from "@/app/components/layout/use-sections";
import { useMe } from "@/app/lib/use-me";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const me = useMe();
  const sections = useSidebarSections();

  if (me.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-500">
        Loading…
      </div>
    );
  }

  if (!me.data?.is_super_admin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white">
        <h1 className="text-2xl font-bold text-ink-900">Admin access required</h1>
        <p className="text-sm text-ink-500">Your account is not on the admin allowlist.</p>
        <Link
          href="/"
          className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
        >
          Back to app
        </Link>
      </div>
    );
  }

  return (
    <SidebarLayout sections={sections}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
