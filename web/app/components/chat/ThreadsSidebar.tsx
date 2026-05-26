import { Plus, MessageSquare } from "lucide-react";


export type Thread = {
  id: string;
  project_id: string;
  name: string;
  status: string;
  langgraph_thread_id: string;
  created_at: string;
  last_active_at: string;
};


export function ThreadsSidebar({
  threads,
  currentThreadId,
  onSelectThread,
  onCreateThread,
}: {
  threads: Thread[];
  currentThreadId: string;
  onSelectThread: (tid: string) => void;
  onCreateThread: () => void;
}) {
  return (
    <aside className="w-52 border-r border-gray-200 bg-gray-50 flex flex-col">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Threads</h3>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {threads.map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelectThread(t.id)}
            className={`flex items-center gap-2 w-full px-4 py-1.5 text-left text-sm hover:bg-gray-100 ${
              t.id === currentThreadId ? "bg-purple-50 text-purple-700 font-medium" : "text-gray-700"
            }`}
          >
            <MessageSquare className="w-3 h-3" />
            <span className="truncate">{t.name}</span>
          </button>
        ))}
      </div>
      <div className="p-3 border-t border-gray-200">
        <button
          type="button"
          onClick={onCreateThread}
          aria-label="new thread"
          className="flex items-center justify-center gap-1 w-full py-1.5 px-2 text-xs text-gray-700 hover:bg-gray-100 rounded border border-dashed border-gray-300"
        >
          <Plus className="w-3 h-3" /> New thread
        </button>
      </div>
    </aside>
  );
}
