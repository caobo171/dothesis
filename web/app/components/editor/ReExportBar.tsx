"use client";


type Props = {
  lastExportAt: Date | null;
  editsSinceExport: number;
  onReExport: () => Promise<void>;
  exporting: boolean;
  error?: Error | null;
};


function _formatRelative(t: Date | null): string {
  if (!t) return "never";
  const diff = Date.now() - t.getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return `${h}h ago`;
}


// Pinned at the top of the editor surface. Always visible.
// Freshness counter (editsSinceExport) is driven by parent watching useChapterAutosave.
export function ReExportBar({ lastExportAt, editsSinceExport, onReExport, exporting, error }: Props) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 px-6 py-3 bg-white">
      <div className="text-sm">
        <span className="text-gray-500">Last export: </span>
        <span className="font-medium text-gray-900">{_formatRelative(lastExportAt)}</span>
        {editsSinceExport > 0 && (
          <span className="text-gray-500 ml-2">· {editsSinceExport} edits since</span>
        )}
        {error && (
          <span className="ml-3 text-red-600 text-xs">Export failed — {error.message}</span>
        )}
      </div>
      <button
        type="button"
        disabled={exporting}
        onClick={onReExport}
        className="text-sm px-4 py-1.5 bg-primary-600 text-white rounded-md font-medium hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {exporting ? "Exporting…" : "Re-export"}
      </button>
    </div>
  );
}
