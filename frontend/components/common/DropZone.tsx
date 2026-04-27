'use client';

import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { clsx } from 'clsx';

// Restricted to PDF and DOCX only — TXT/MD removed per product decision since
// users with plain text can use the Paste tab directly.
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
};

interface DropZoneProps {
  onFile: (file: File) => void;
  uploading?: boolean;
}

export function DropZone({ onFile, uploading }: DropZoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) onFile(accepted[0]);
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: 10 * 1024 * 1024,
    multiple: false,
  });

  return (
    <div
      {...getRootProps()}
      className={clsx(
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition',
        isDragActive ? 'border-primary bg-bg-blue' : 'border-rule hover:border-ink-muted',
        uploading && 'opacity-50 pointer-events-none'
      )}
    >
      <input {...getInputProps()} />
      <div className="text-ink-muted text-sm">
        {isDragActive ? (
          <p>Drop your file here</p>
        ) : (
          <>
            <p className="font-medium text-ink-soft">Drag & drop your file</p>
            <p className="mt-1 text-xs">PDF or DOCX (max 10 MB)</p>
          </>
        )}
      </div>
    </div>
  );
}
