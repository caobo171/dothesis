import { X, FileText, Loader } from "lucide-react";


export type UploadChipProps = {
  filename: string;
  pageCount: number | null;
  status: "uploading" | "extracting" | "ready" | "error";
  onDelete: () => void;
};


export function UploadChip({ filename, pageCount, status, onDelete }: UploadChipProps) {
  return (
    <div className="inline-flex items-center gap-2 px-2 py-1 rounded-md border border-gray-200 bg-gray-50 text-xs">
      {/* Spinner while in-progress, document icon when settled */}
      {status === "uploading" || status === "extracting" ? (
        <Loader className="w-3 h-3 animate-spin text-gray-500" />
      ) : (
        <FileText className="w-3 h-3 text-gray-500" />
      )}
      <span className="font-medium text-gray-800 max-w-[180px] truncate">{filename}</span>
      <span className="text-gray-500">
        {status === "uploading" && "uploading…"}
        {status === "extracting" && "extracting…"}
        {status === "ready" && pageCount && `${pageCount} pages`}
        {status === "ready" && !pageCount && "ready"}
        {status === "error" && "failed"}
      </span>
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Delete ${filename}`}
        className="ml-1 text-gray-400 hover:text-red-500"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
