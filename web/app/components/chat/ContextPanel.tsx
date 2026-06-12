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


// Brief §1.4 — per-module workflow status from the API (PR #2 wires
// projects.module_status into the GET /projects/{id} response). Empty
// dict {} during the dual-write window for projects that haven't seen
// a turn yet; in that case we fall back to the legacy context-store
// derivation so the panel still shows something sensible.
export type ModuleStatusMap = Partial<Record<"M1" | "M2" | "M3" | "M4" | "M5", string>>;


// Derive display status. Precedence:
//   1. module_status[M] === "needs_review" (brief §1.5 ⚠) → needs_attention
//   2. data.confirmed_at → done
//   3. isCurrent (the conversation focus) → active
//   4. otherwise → locked (soft lock per brief §8.4)
//
// We don't reuse statusFor for the legacy `active` path because that's
// derived from `currentModule`/`focus` (passed in), while `needs_review`
// is a separate signal from the new module_status map that wins over both.
function statusFor(
  data: Record<string, unknown> | null,
  isCurrent: boolean,
  moduleStatus: string | undefined,
): ModuleStatus {
  if (moduleStatus === "needs_review") return "needs_attention";
  if (!data) return "locked";
  if (data.confirmed_at) return "done";
  return isCurrent ? "active" : "locked";
}


export function ContextPanel({
  contextStore,
  uploads,
  currentModule,
  moduleStatus,
}: {
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
  // PR #2 wiring — projects.module_status from GET /projects/{id}. Optional
  // for backward compat with callers that haven't been updated yet; when
  // absent, statusFor falls back to the legacy derivation.
  moduleStatus?: ModuleStatusMap;
}) {
  // Determine active module: explicit override or first unconfirmed module
  const nextUnconfirmed = MODULES.find(m => !contextStore[m.key]?.confirmed_at)?.module;
  const active = currentModule ?? nextUnconfirmed;

  // 2026-06-10 — DoThesis.html design: the right rail is the module tracker
  // (numbered status badges + vertical track), with the slice viewers and
  // uploads below. Palette moved from gray-* to the ink/primary tokens.
  return (
    <aside className="w-72 border-l border-ink-200 bg-white overflow-y-auto">
      <div className="px-4 pt-3.5 pb-1 flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-[0.1em] text-ink-500 font-bold">Workflow</h3>
        <span className="text-[11px] text-ink-400">
          {MODULES.filter(m => contextStore[m.key]?.confirmed_at).length} / {MODULES.length}
        </span>
      </div>
      <div className="px-1.5 py-1.5">
        {MODULES.map((m, i) => (
          <ModuleProgressDot
            key={m.module}
            module={m.module}
            label={m.label}
            isLast={i === MODULES.length - 1}
            status={statusFor(
              contextStore[m.key],
              m.module === active,
              moduleStatus?.[m.module as keyof ModuleStatusMap],
            )}
          />
        ))}
      </div>
      <div className="px-4 pt-3 pb-1 border-t border-ink-100">
        <h3 className="text-[11px] uppercase tracking-[0.1em] text-ink-500 font-bold">Context store</h3>
      </div>
      <div className="py-1">
        {MODULES.map(m => (
          <ContextModuleViewer
            key={m.module}
            module={m.module}
            label={m.label}
            data={contextStore[m.key]}
          />
        ))}
      </div>
      {uploads.length > 0 && (
        <div className="px-4 py-3 border-t border-ink-100">
          <h3 className="text-[11px] uppercase tracking-[0.1em] text-ink-500 font-bold mb-2">
            Uploads ({uploads.length})
          </h3>
          {uploads.map(u => (
            <div key={u.id} className="text-xs text-ink-700 truncate py-0.5">
              {u.filename}
              {u.page_count && <span className="text-ink-400 ml-1">· {u.page_count}p</span>}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
