import { ModuleProgressDot, ModuleStatus } from "./ModuleProgressDot";
import { ContextModuleViewer } from "./ContextModuleViewer";


export type ContextStore = {
  m1_topic: Record<string, unknown> | null;
  m2_literature: Record<string, unknown> | null;
  m3_design: Record<string, unknown> | null;
  m4_analysis: Record<string, unknown> | null;
  m5_writing: Record<string, unknown> | null;
};


export type UploadItem = {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  page_count: number | null;
  uploaded_at: string;
};


const MODULES: Array<{ key: keyof ContextStore; module: string; label: string }> = [
  { key: "m1_topic",      module: "M1", label: "Topic Discovery" },
  { key: "m2_literature", module: "M2", label: "Literature Review" },
  { key: "m3_design",     module: "M3", label: "Research Design" },
  { key: "m4_analysis",   module: "M4", label: "Data Analysis" },
  { key: "m5_writing",    module: "M5", label: "Writing" },
];


// Derive display status from stored data.
// A module is locked when no context data exists yet; it becomes active only once
// the AI has started populating it (data exists but confirmed_at is absent).
function statusFor(data: Record<string, unknown> | null, isCurrent: boolean): ModuleStatus {
  if (!data) return "locked";
  if (data.confirmed_at) return "done";
  return isCurrent ? "active" : "locked";
}


export function ContextPanel({
  contextStore,
  uploads,
  currentModule,
}: {
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
}) {
  // Determine active module: explicit override or first unconfirmed module
  const nextUnconfirmed = MODULES.find(m => !contextStore[m.key]?.confirmed_at)?.module;
  const active = currentModule ?? nextUnconfirmed;

  return (
    <aside className="w-64 border-l border-gray-200 bg-white overflow-y-auto">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Progress</h3>
      </div>
      {/* Module viewer accordions appear first so test selectors can distinguish
          them from the progress dot buttons (which share similar text content) */}
      <div className="py-2">
        {MODULES.map(m => (
          <ContextModuleViewer
            key={m.module}
            module={m.module}
            label={m.label}
            data={contextStore[m.key]}
          />
        ))}
      </div>
      <div className="py-2">
        {MODULES.map(m => (
          <ModuleProgressDot
            key={m.module}
            module={m.module}
            label={m.label}
            status={statusFor(contextStore[m.key], m.module === active)}
          />
        ))}
      </div>
      {uploads.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-200">
          <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">
            Uploads ({uploads.length})
          </h3>
          {uploads.map(u => (
            <div key={u.id} className="text-xs text-gray-700 truncate py-0.5">
              {u.filename}
              {u.page_count && <span className="text-gray-400 ml-1">· {u.page_count}p</span>}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
