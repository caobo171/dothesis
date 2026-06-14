import { ReactNode } from "react";

// Minimal layout — the editor surface is full-height and manages its own
// navigation. We don't reuse the chat shell here because the editor's outline
// rail replaces the threads sidebar.
//
// Height must be bounded (h-full, not min-h-screen): the ancestor chat shell is
// `h-screen overflow-hidden`, so a min-height container grows past the viewport
// and its content is clipped with no way to scroll. h-full pins this to the
// parent's height so ChapterEditor's inner overflow-y-auto can actually scroll.
export default function EditorLayout({ children }: { children: ReactNode }) {
  return <div className="bg-white h-full overflow-hidden">{children}</div>;
}
