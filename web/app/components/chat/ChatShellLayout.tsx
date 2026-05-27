"use client";

import { ReactNode } from "react";


export function ChatShellLayout({
  leftPane,
  rightPane,
  children,
}: {
  leftPane: ReactNode;
  rightPane: ReactNode;
  // Center pane: header + message list + chat input stacked as a flex column
  children: ReactNode;
}) {
  return (
    <div className="flex h-[calc(100vh-4rem)] bg-white">
      {/* Left pane — threads — hidden below lg to preserve mobile screen space */}
      <div className="hidden lg:flex flex-shrink-0">{leftPane}</div>

      {/* Middle pane — chat */}
      <main className="flex-1 flex flex-col min-w-0">{children}</main>

      {/* Right pane — context — hidden below lg to preserve mobile screen space */}
      <div className="hidden lg:flex flex-shrink-0">{rightPane}</div>
    </div>
  );
}
