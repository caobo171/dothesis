"use client";

import {
  CpuChipIcon,
  CreditCardIcon,
  DocumentTextIcon,
  LinkIcon,
  NewspaperIcon,
  PuzzlePieceIcon,
  RectangleStackIcon,
  SpeakerWaveIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import { useMemo } from "react";

import type { SidebarSection } from "@/app/components/layout/sections";
import { useT } from "@/app/lib/i18n/LocaleProvider";

/**
 * The operator's nav, and only the operator's nav.
 *
 * These seven entries used to be appended to `useSidebarSections` — the
 * student menu — behind an `is_super_admin` check, so an admin browsing their
 * own thesis carried Users/Jobs/Orders in the sidebar all the way through the
 * product, and /admin/users rendered inside the same shell as /papers with
 * Dashboard and Humanize still listed above it. One menu answering to two jobs
 * meant every admin destination had to be named so it could not be mistaken
 * for its student counterpart ("All tool usage" vs "Tool usage"), which is a
 * workaround for the shells being fused rather than a naming problem.
 *
 * Split apart, each shell lists what its own job needs. The console is reached
 * from the one Admin entry that remains in the student menu, and `Back to app`
 * in the admin shell returns.
 *
 * Labels come from the message catalogue for the same reason the student menu's
 * do: an English literal here is an English literal on a Vietnamese-primary
 * product. `name` therefore holds an already translated string.
 */
export function useAdminSections(): SidebarSection[] {
  const t = useT();
  return useMemo(
    () => [
      {
        // The blog is a content surface with its own editorial workflow, so it
        // reads first and separately from the operational tables below it.
        id: "content",
        name: t("nav.content"),
        options: [
          { name: t("nav.blogPosts"), href: "/admin/blog", icon: NewspaperIcon },
          { name: t("nav.blogCategories"), href: "/admin/blog/categories", icon: RectangleStackIcon },
        ],
      },
      {
        id: "people",
        name: t("nav.people"),
        options: [
          // `default` here, not on the blog: /admin still redirects to
          // /admin/users, and the highlighted entry has to be the one you
          // actually land on.
          { name: t("nav.users"), href: "/admin/users", icon: UserIcon, default: true },
          { name: t("nav.orders"), href: "/admin/orders", icon: CreditCardIcon },
        ],
      },
      {
        id: "operations",
        name: t("nav.operations"),
        options: [
          { name: t("nav.papers"), href: "/admin/papers", icon: DocumentTextIcon },
          { name: t("nav.jobs"), href: "/admin/jobs", icon: CpuChipIcon },
          // Plain "Tool usage" again, not "All tool usage": the disambiguation
          // only existed because the student entry sat in the same menu.
          { name: t("nav.toolUsage"), href: "/admin/tools", icon: PuzzlePieceIcon },
          { name: t("nav.announcements"), href: "/admin/announcements", icon: SpeakerWaveIcon },
          { name: t("nav.connectors"), href: "/admin/connectors", icon: LinkIcon },
        ],
      },
    ],
    [t],
  );
}
