"use client";

import { ReactNode, useState } from "react";


export function FileDropZone({
  onFileDrop,
  children,
}: {
  onFileDrop: (files: File[]) => void;
  children: ReactNode;
}) {
  const [dragging, setDragging] = useState(false);

  return (
    <div
      data-testid="file-drop-zone"
      onDragEnter={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={e => { e.preventDefault(); setDragging(false); }}
      onDragOver={e => e.preventDefault()}
      onDrop={e => {
        e.preventDefault();
        setDragging(false);
        // Extract files from the drop event and forward to parent handler
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) onFileDrop(files);
      }}
      className={`relative ${dragging ? "ring-2 ring-purple-400 ring-offset-1" : ""}`}
    >
      {children}
      {dragging && (
        <div className="absolute inset-0 bg-purple-50/80 pointer-events-none flex items-center justify-center text-sm text-purple-700 font-medium z-10">
          Drop PDFs here
        </div>
      )}
    </div>
  );
}
