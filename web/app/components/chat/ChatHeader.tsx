import { ReactNode } from "react";


export function ChatHeader({
  projectName,
  threadName,
  autoDraftButton,
}: {
  projectName: string;
  threadName: string;
  // Slot for the auto-draft trigger button — kept as a render prop so the
  // header stays a pure presentational component with no hook dependencies.
  autoDraftButton: ReactNode;
}) {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold text-gray-900">{projectName}</span>
        <span className="text-gray-300">·</span>
        <span className="text-sm text-gray-600">{threadName}</span>
      </div>
      <div>{autoDraftButton}</div>
    </header>
  );
}
