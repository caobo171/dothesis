"use client";

import {
  ClockIcon,
  CpuChipIcon,
  PuzzlePieceIcon,
  CreditCardIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  HomeIcon,
  LinkIcon,
  ShieldCheckIcon,
  SpeakerWaveIcon,
  WrenchScrewdriverIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import { useMemo } from "react";

import { useMe } from "@/app/lib/use-me";

import type { SidebarSection } from "./sections";

/**
 * Single source of truth for the sidebar nav. Both (inapp) and admin
 * layouts use this so the menu looks identical across both shells —
 * admin entries appear inline only when useMe().data.is_super_admin.
 */
export function useSidebarSections(): SidebarSection[] {
  const me = useMe();
  return useMemo(() => {
    const sections: SidebarSection[] = [
      {
        id: "workspace",
        name: "Workspace",
        options: [
          { name: "Dashboard", href: "/", icon: HomeIcon, default: true },
          { name: "Theses", href: "/papers", icon: DocumentTextIcon },
          // Under WORKSPACE, next to the thesis surfaces: these are standalone
          // jobs (text in, answer out, no project) rather than an account
          // setting. The agent remains the main surface — this is the door for
          // work that needs no thesis context.
          { name: "Tools", href: "/tools", icon: WrenchScrewdriverIcon },
        ],
      },
      {
        id: "account",
        name: "Account",
        options: [
          { name: "Credit", href: "/credit", icon: CurrencyDollarIcon },
          { name: "Transactions", href: "/transactions", icon: ClockIcon },
          // Under ACCOUNT, not ADMIN: connecting Claude/ChatGPT is a per-user
          // action (each person adds the connector in their own client), not
          // something an operator does once for everybody.
          // href is /connect, NOT /mcp — /mcp is the MCP PROTOCOL endpoint that
          // Claude connects to. A guide page sitting on that path would shadow
          // the server and hand connectors an HTML page.
          { name: "MCP", href: "/connect", icon: PuzzlePieceIcon },
        ],
      },
    ];

    if (me.data?.is_super_admin) {
      sections.push({
        id: "admin",
        name: "Admin",
        options: [
          { name: "Users", href: "/admin/users", icon: UserIcon },
          { name: "Papers", href: "/admin/papers", icon: DocumentTextIcon },
          { name: "Jobs", href: "/admin/jobs", icon: CpuChipIcon },
          { name: "Announcements", href: "/admin/announcements", icon: SpeakerWaveIcon },
          { name: "Orders", href: "/admin/orders", icon: CreditCardIcon },
          { name: "Connectors", href: "/admin/connectors", icon: LinkIcon },
        ],
      });
    }

    return sections;
  }, [me.data?.is_super_admin]);
}

// Re-export for layouts that want a quick consistent icon reference
export { ShieldCheckIcon };
