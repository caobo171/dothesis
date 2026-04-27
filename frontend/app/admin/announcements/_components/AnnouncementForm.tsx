// frontend/app/admin/announcements/_components/AnnouncementForm.tsx
//
// Shared create/edit form. Uses controlled inputs (no react-hook-form)
// because the form has only six fields and react-hook-form would add weight
// without buying ergonomics here.

'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'react-toastify';
import AdminApi from '@/lib/admin/api';

export type AnnouncementFormValue = {
  id?: string;
  title: string;
  content: string;
  audience: 'all' | 'free' | 'paid';
  enabled: boolean;
  startsAt?: string;
  endsAt?: string;
};

type Props = {
  initial: AnnouncementFormValue;
  // 'create' uses /announcements/create; 'update' uses /announcements/update + id.
  mode: 'create' | 'update';
};

export function AnnouncementForm({ initial, mode }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [v, setV] = useState<AnnouncementFormValue>(initial);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!v.title.trim()) {
      toast.error('Title is required');
      return;
    }
    setBusy(true);
    try {
      const url = mode === 'create' ? '/api/admin/announcements/create' : '/api/admin/announcements/update';
      const payload: Record<string, any> = {
        title: v.title,
        content: v.content,
        audience: v.audience,
        enabled: v.enabled,
        startsAt: v.startsAt || '',
        endsAt: v.endsAt || '',
      };
      if (mode === 'update' && v.id) payload.id = v.id;
      const res = await AdminApi.post(url, payload);
      if (res.code !== 1) {
        toast.error(res.message || 'Save failed');
        return;
      }
      toast.success(mode === 'create' ? 'Created' : 'Updated');
      router.push('/admin/announcements');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
      <div>
        <label className="block text-xs font-medium text-gray-600">Title</label>
        <input
          type="text"
          value={v.title}
          onChange={(e) => setV({ ...v, title: e.target.value })}
          className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          placeholder="Short headline"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600">Content (markdown supported)</label>
        <textarea
          value={v.content}
          onChange={(e) => setV({ ...v, content: e.target.value })}
          rows={8}
          className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm"
          placeholder="What do you want everyone to see?"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600">Audience</label>
          <select
            value={v.audience}
            onChange={(e) => setV({ ...v, audience: e.target.value as any })}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="all">Everyone</option>
            <option value="free">Free plan only</option>
            <option value="paid">Paid plans only</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600">Enabled</label>
          <select
            value={v.enabled ? 'true' : 'false'}
            onChange={(e) => setV({ ...v, enabled: e.target.value === 'true' })}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="false">Off</option>
            <option value="true">On</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600">Starts at (optional)</label>
          <input
            type="datetime-local"
            value={v.startsAt || ''}
            onChange={(e) => setV({ ...v, startsAt: e.target.value })}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600">Ends at (optional)</label>
          <input
            type="datetime-local"
            value={v.endsAt || ''}
            onChange={(e) => setV({ ...v, endsAt: e.target.value })}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => router.push('/admin/announcements')}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  );
}

export default AnnouncementForm;
