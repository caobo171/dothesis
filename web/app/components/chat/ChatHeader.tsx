import Link from "next/link";
import { ReactNode } from "react";


export function ChatHeader({
  projectName,
  threadName,
  autoDraftButton,
  projectId,
  hasChapters,
}: {
  projectName: string;
  threadName: string;
  // Slot for the auto-draft trigger button — kept as a render prop so the
  // header stays a pure presentational component with no hook dependencies.
  autoDraftButton: ReactNode;
  // Optional: when provided, enables the "Open editor" shortcut button.
  projectId?: string;
  // Gate: show "Open editor" only once the project has at least one chapter,
  // so the link is never dangling for brand-new projects.
  hasChapters?: boolean;
}) {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold text-gray-900">{projectName}</span>
        <span className="text-gray-300">·</span>
        <span className="text-sm text-gray-600">{threadName}</span>
      </div>
      <div className="flex items-center gap-2">
        {/* "Open editor" is only shown once chapters exist — avoids a dead
            link for new projects that have no content to edit yet. */}
        {hasChapters && projectId && (
          <Link
            href={`/chat/projects/${projectId}/editor`}
            className="inline-flex items-center px-3 py-1 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700"
          >
            Open editor
          </Link>
        )}
        {autoDraftButton}
      </div>
    </header>
  );
}
