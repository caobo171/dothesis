export type ModuleStatus = "done" | "active" | "locked" | "needs_attention";

// Maps each status to a Tailwind background class for the indicator dot
const COLOR_BY_STATUS: Record<ModuleStatus, string> = {
  done: "bg-green-500",
  active: "bg-amber-500",
  locked: "bg-gray-300",
  needs_attention: "bg-red-500",
};


export function ModuleProgressDot({
  module,
  status,
  label,
  onClick,
}: {
  module: string;
  status: ModuleStatus;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 w-full text-left py-1 px-2 rounded hover:bg-gray-50 transition-colors"
    >
      <span
        data-testid={`dot-${module}`}
        className={`inline-block w-2 h-2 rounded-full ${COLOR_BY_STATUS[status]}`}
      />
      <span className="text-xs font-medium text-gray-700">{module}</span>
      <span className="text-xs text-gray-500 truncate">{label}</span>
    </button>
  );
}
