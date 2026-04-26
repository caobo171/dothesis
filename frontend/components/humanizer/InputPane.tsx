'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setInputText, setInputSource } from '@/store/slices/humanizerSlice';
import { DropZone } from '@/components/common/DropZone';
import { UrlImport } from '@/components/common/UrlImport';
import { clsx } from 'clsx';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

const TABS = [
  { value: 'paste' as const, label: 'Paste text' },
  { value: 'upload' as const, label: 'Upload file' },
  { value: 'url' as const, label: 'Import URL' },
];

export function InputPane() {
  const dispatch = useDispatch();
  const { inputText, inputSource } = useSelector((s: RootState) => s.humanizer);
  const [uploading, setUploading] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await Fetch.postWithAccessToken<any>('/api/document/upload', formData);
      if (res.data.code === Code.Success) {
        dispatch(setInputText(res.data.data.content));
        dispatch(setInputSource('paste'));
        toast.success(`Loaded ${res.data.data.wordCount} words`);
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Upload failed');
    }
    setUploading(false);
  };

  const handleUrlImport = (content: string) => {
    dispatch(setInputText(content));
    dispatch(setInputSource('paste'));
  };

  const wordCount = inputText.trim().split(/\s+/).filter(Boolean).length;

  return (
    <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-rule">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => dispatch(setInputSource(tab.value))}
            className={clsx(
              'px-4 py-2.5 text-xs font-medium transition border-b-2',
              inputSource === tab.value
                ? 'border-primary text-primary'
                : 'border-transparent text-ink-muted hover:text-ink-soft'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 p-4">
        {inputSource === 'paste' && (
          <textarea
            value={inputText}
            onChange={(e) => dispatch(setInputText(e.target.value))}
            placeholder="Paste your text here..."
            className="w-full h-full min-h-[300px] resize-none outline-none text-sm text-ink leading-relaxed"
          />
        )}
        {inputSource === 'upload' && <DropZone onFile={handleFile} uploading={uploading} />}
        {inputSource === 'url' && <UrlImport onImport={handleUrlImport} />}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-rule flex items-center justify-between">
        <span className="text-xs text-ink-muted font-mono">{wordCount} words</span>
      </div>
    </div>
  );
}
