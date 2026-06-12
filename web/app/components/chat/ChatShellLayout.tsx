"use client";

import { ReactNode } from "react";


/**
 * Three-pane chat shell after the design pivot:
 *   - leftPane    project sidebar (WorkflowSidebar) — Threads + Workflow tabs
 *   - middle      chat (header + messages + composer)
 *   - rightPane   ContextPanel (live context_store viewer)
 *
 * The earlier right-side threads drawer is gone — threads now live inside
 * the same sidebar as the workflow rail (toggled via a tab). This file
 * stays small on purpose: it's three flex children + global height. No
 * portal, no drawer state, no toggle handle.
 */
export function ChatShellLayout({
  leftPane,
  rightPane,
  children,
}: {
  leftPane: ReactNode;
  rightPane: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen bg-white">
      {leftPane}
      <main className="flex-1 flex flex-col min-w-0">{children}</main>
      <div className="hidden lg:flex flex-shrink-0">{rightPane}</div>
    </div>
  );
}
