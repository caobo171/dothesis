"use client";

import {
  CpuChipIcon,
  CreditCardIcon,
  DocumentTextIcon,
  SpeakerWaveIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import Link from "next/link";
import type { ReactNode } from "react";

import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import type { SidebarSection } from "@/app/components/layout/sections";
import { useMe } from "@/app/lib/use-me";

const SECTIONS: SidebarSection[] = [
  {
    id: "admin",
    name: "Admin",
    options: [
      { name: "Users", href: "/admin/users", icon: UserIcon },
      { name: "Papers", href: "/admin/papers", icon: DocumentTextIcon },
      { name: "Jobs", href: "/admin/jobs", icon: CpuChipIcon },
      { name: "Announcements", href: "/admin/announcements", icon: SpeakerWaveIcon },
      { name: "Orders", href: "/admin/orders", icon: CreditCardIcon },
    ],
  },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const me = useMe();

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

  return <SidebarLayout sections={SECTIONS}>{children}</SidebarLayout>;
}
