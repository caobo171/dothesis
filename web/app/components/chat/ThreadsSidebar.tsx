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


// 2026-06-10 — restyled to the DoThesis.html sidebar idiom: white surface,
// uppercase section label, rounded rows with primary-50 active state, pill
// "New thread" button. Behavior unchanged.
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
    <aside className="w-52 border-r border-ink-200 bg-white flex flex-col">
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
      <div className="p-3 border-t border-ink-100">
        <button
          type="button"
          onClick={onCreateThread}
          aria-label="new thread"
          className="flex items-center justify-center gap-1.5 w-full py-2 px-2 text-xs font-semibold text-ink-700 hover:bg-ink-50 hover:border-ink-400 rounded-full border border-dashed border-ink-300 transition-colors"
        >
          <Plus className="w-3 h-3" /> New thread
        </button>
      </div>
    </aside>
  );
}
