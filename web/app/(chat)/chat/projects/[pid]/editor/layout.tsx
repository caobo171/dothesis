import { ReactNode } from "react";

// Minimal layout — the editor surface is full-height and manages its own
// navigation. We don't reuse the chat shell here because the editor's outline
// rail replaces the threads sidebar.
export default function EditorLayout({ children }: { children: ReactNode }) {
  return <div className="bg-white min-h-screen">{children}</div>;
}
