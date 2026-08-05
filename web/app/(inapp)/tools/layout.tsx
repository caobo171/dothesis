"use client";

import type { ReactNode } from "react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

/**
 * Shell shared by every tool page.
 *
 * The in-page tool rail used to live here as a second list of the same three
 * tools. It was removed when they were promoted into the sidebar: the master
 * nav IS the rail now, and showing both meant the page repeated the menu that
 * was already open beside it.
 *
 * The blurb stays, once, above whichever tool is open, because it draws the
 * boundary that keeps students out of the wrong surface — anything that needs
 * to know their research belongs in a thesis thread, not here.
 */
export default function ToolsLayout({ children }: { children: ReactNode }) {
  const t = useT();

  return (
    <div className="max-w-4xl mx-auto">
      <p className="mt-0 mb-5 text-[13px] text-ink-500 max-w-2xl leading-relaxed">
        {t("tools.blurb")}
      </p>
      {children}
    </div>
  );
}
