"use client";

import {
  BookOpenIcon,
  ClockIcon,
  PuzzlePieceIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  HomeIcon,
  ShieldCheckIcon,
  WrenchScrewdriverIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { useMemo } from "react";

import { useT } from "@/app/lib/i18n/LocaleProvider";
import { useMe } from "@/app/lib/use-me";

import type { SidebarSection } from "./sections";

/**
 * The STUDENT sidebar — the (inapp) shell's menu, and nothing else.
 *
 * It used to serve the admin layout too, appending the console's tables when
 * useMe().data.is_super_admin. The console has its own shell and its own nav
 * now (app/admin/_components/use-admin-sections.ts); what survives here is one
 * Admin entry pointing at its door.
 *
 * Labels come from the message catalogue, not literals: this hook is the ONLY
 * place the master nav is spelled out, so an English literal here shows up on
 * every page of a Vietnamese-primary product. `name` therefore holds an already
 * translated string — SidebarLayout renders it as-is and never translates.
 */
export function useSidebarSections(): SidebarSection[] {
  const me = useMe();
  const t = useT();
  return useMemo(() => {
    const sections: SidebarSection[] = [
      {
        id: "workspace",
        name: t("nav.workspace"),
        options: [
          { name: t("nav.dashboard"), href: "/", icon: HomeIcon, default: true },
          { name: t("nav.theses"), href: "/papers", icon: DocumentTextIcon },
        ],
      },
      // Each tool is its own menu entry, not one "Tools" door.
      //
      // A single item hid these products behind a word: a student who wants to
      // humanize a paragraph has to guess that "Tools" contains it. This is how
      // every competitor in the category presents the same jobs (QuillBot lists
      // Paraphraser / AI Detector / AI Humanizer as sibling nav items), and it
      // is what a student arriving with one specific job in mind scans for.
      //
      // The agent is still the product — these stay BELOW Workspace so the
      // thesis surfaces read first.
      //
      // NOT listed: /tools/rhythm. It has no counterpart in any competitor's
      // menu because it isn't a product — it is the stylometric referee from
      // the humanize loop (orchestrator/tools/detector.py) with a door on it,
      // and detector.py's own comment calls that signal "not to trust as a
      // verdict". A menu entry nobody can name the purpose of costs more
      // attention than the tool returns. The route and the endpoint both stay
      // live for the MCP connector and for anyone holding the link.
      {
        id: "tools",
        name: t("tools.title"),
        options: [
          { name: t("tools.humanize.name"), href: "/tools/humanize", icon: SparklesIcon },
          { name: t("tools.citation.name"), href: "/tools/citation", icon: BookOpenIcon },
          // NOT listed: /tools/similarity. Same treatment as /tools/rhythm —
          // the route and the endpoint stay live for the MCP connector and
          // for anyone holding the link. It is a self-check over the
          // student's own file (repeats + quotation/reference agreement),
          // not a similarity percentage, and without a configured corpus
          // provider the name cannot back up what a student scanning this
          // menu expects. Hide the door; keep the tool.
          // The student's own runs, alongside the tools that produce them.
          // /admin/tools has shown operators every run since it shipped; the
          // person who paid for one could only see it as a footnote under the
          // credit ledger. It is a destination now because it has to be: the
          // stored input and output are downloaded here, a document is re-run
          // here, and a run in flight reports its progress here.
          { name: t("nav.toolUsage"), href: "/tool-runs", icon: WrenchScrewdriverIcon },
        ],
      },
      {
        id: "account",
        name: t("nav.account"),
        options: [
          { name: t("nav.credit"), href: "/credit", icon: CurrencyDollarIcon },
          { name: t("nav.transactions"), href: "/transactions", icon: ClockIcon },
          // Under ACCOUNT, not ADMIN: connecting Claude/ChatGPT is a per-user
          // action (each person adds the connector in their own client), not
          // something an operator does once for everybody.
          // href is /connect, NOT /mcp — /mcp is the MCP PROTOCOL endpoint that
          // Claude connects to. A guide page sitting on that path would shadow
          // the server and hand connectors an HTML page.
          { name: t("nav.mcp"), href: "/connect", icon: PuzzlePieceIcon },
        ],
      },
    ];

    if (me.data?.is_super_admin) {
      // ONE door, not the seven destinations this used to splice in.
      //
      // The console has its own shell now (app/admin/_components/
      // use-admin-sections.ts). Listing its tables here as well would put
      // Users/Jobs/Orders in the sidebar of an admin who is writing their own
      // thesis, and would mean the product's main menu changes shape depending
      // on who is signed in — which is what made an admin's view of the app
      // something nobody could reason about from the student's.
      sections.push({
        id: "admin",
        name: t("nav.admin"),
        options: [
          { name: t("nav.adminConsole"), href: "/admin", icon: ShieldCheckIcon },
        ],
      });
    }

    return sections;
    // `t` is memoised per locale by LocaleProvider, so this recomputes on a
    // language switch and at no other time.
  }, [me.data?.is_super_admin, t]);
}
