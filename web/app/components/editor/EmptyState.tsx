import Link from "next/link";


// Editor route is always reachable; this surface appears when m5_writing.chapters
// is empty (M5 hasn't run or is mid-stream). Keeps the entry point predictable
// while pointing the user to where work actually happens.
export function EmptyState({ projectId }: { projectId: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-2">No chapters yet</h2>
      <p className="text-gray-600 mb-6 max-w-md">
        M5 hasn't drafted your chapters yet. Open the chat to start the writing module —
        the editor will populate as M5 produces each chapter.
      </p>
      <Link
        href={`/chat/projects/${projectId}`}
        className="inline-flex items-center px-4 py-2 bg-purple-600 text-white rounded-md text-sm font-medium hover:bg-purple-700"
      >
        Open chat
      </Link>
    </div>
  );
}
