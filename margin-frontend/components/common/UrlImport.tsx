'use client';

import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

interface UrlImportProps {
  onImport: (content: string, title: string) => void;
}

export function UrlImport({ onImport }: UrlImportProps) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);

  const handleFetch = async () => {
    if (!url.trim()) return;
    setLoading(true);
    try {
      const res = await Fetch.postWithAccessToken<any>('/api/document/import-url', { url });
      if (res.data.code === Code.Success) {
        onImport(res.data.data.content, res.data.data.title);
        toast.success('Content imported');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Failed to import URL');
    }
    setLoading(false);
  };

  return (
    <div className="flex gap-2">
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://example.com/article"
        className="flex-1 px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
      />
      <button
        onClick={handleFetch}
        disabled={loading || !url.trim()}
        className="px-4 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition disabled:opacity-50"
      >
        {loading ? 'Fetching...' : 'Fetch'}
      </button>
    </div>
  );
}
