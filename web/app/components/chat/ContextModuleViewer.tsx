import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";


export function ContextModuleViewer({
  module,
  label,
  data,
}: {
  module: string;
  label: string;
  data: Record<string, unknown> | null;
}) {
  const [open, setOpen] = useState(false);
  // Return nothing when module has no data yet — nothing to display
  if (!data) return null;

  return (
    <div className="border-t border-ink-100 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-2 py-1.5 text-left hover:bg-ink-50 text-xs"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <span className="font-medium">{module} · {label}</span>
      </button>
      {open && (
        <pre className="text-[10px] text-ink-700 px-2 py-2 bg-ink-50 overflow-x-auto max-h-48 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
