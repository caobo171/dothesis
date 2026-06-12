import { MessageSquare } from "lucide-react";


export type Thread = {
  id: string;
  project_id: string;
  name: string;
  status: string;
  langgraph_thread_id: string;
  created_at: string;
  last_active_at: string;
};


// Threads list. The "+ New thread" button used to live in the bottom
// footer here; design feedback was that it should be accessible without
// having to open the threads drawer first. It now sits in
// ChatShellLayout next to the drawer toggle — see `onNewThread` prop.
// `onCreateThread` kept on the type for back-compat with tests but is
// optional now and not rendered inside this component.
export function ThreadsSidebar({
  threads,
  currentThreadId,
  onSelectThread,
}: {
  threads: Thread[];
  currentThreadId: string;
  onSelectThread: (tid: string) => void;
  // Legacy: kept so existing call sites don't have to drop the prop in
  // the same diff. ChatShellLayout consumes it directly now.
  onCreateThread?: () => void;
}) {
  return (
    <aside className="w-52 bg-white flex flex-col h-full">
      <div className="px-4 pt-3.5 pb-2">
        <h3 className="text-[11px] uppercase tracking-[0.1em] text-ink-500 font-bold">Threads</h3>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {threads.map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelectThread(t.id)}
            className={`flex items-center gap-2 w-full px-3 py-2 text-left text-[13px] rounded-xl transition-colors ${
              t.id === currentThreadId
                ? "bg-primary-50 text-primary-700 font-semibold"
                : "text-ink-700 font-medium hover:bg-ink-50"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{t.name}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
