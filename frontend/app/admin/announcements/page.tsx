// frontend/app/admin/announcements/page.tsx
//
// Super-admin-only list and inline edit. Each row has an enabled toggle that
// hits /admin/announcements/toggle without leaving the page.

'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import AdminPageHeader from '../_components/AdminPageHeader';
import AdminTable, { Column } from '../_components/AdminTable';
import StatusBadge from '../_components/StatusBadge';
import ConfirmDialog from '../_components/ConfirmDialog';
import useAdminList from '../_components/useAdminList';
import AdminApi from '@/lib/admin/api';

type Announcement = {
  id: string;
  _id: string;
  title: string;
  content: string;
  audience: 'all' | 'free' | 'paid';
  enabled: boolean;
  startsAt?: string;
  endsAt?: string;
  createdBy: string;
  createdAt: string;
};

export default function AdminAnnouncementsPage() {
  const router = useRouter();
  const { items, total, isLoading, mutate } = useAdminList<Announcement>('/api/admin/announcements', {});

  const [deleting, setDeleting] = useState<Announcement | null>(null);
  const [busy, setBusy] = useState(false);

  const onToggle = async (a: Announcement) => {
    const res = await AdminApi.post('/api/admin/announcements/toggle', { id: a.id, enabled: !a.enabled });
    if (res.code !== 1) {
      toast.error(res.message || 'Toggle failed');
      return;
    }
    await mutate();
  };

  const onDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      const res = await AdminApi.post('/api/admin/announcements/delete', { id: deleting.id });
      if (res.code !== 1) {
        toast.error(res.message || 'Delete failed');
        return;
      }
      toast.success('Deleted');
      setDeleting(null);
      await mutate();
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<Announcement>[] = [
    { key: 'title', header: 'Title', render: (a) => <span className="font-medium text-gray-900">{a.title}</span> },
    {
      key: 'audience',
      header: 'Audience',
      render: (a) => (
        <StatusBadge tone={a.audience === 'all' ? 'gray' : a.audience === 'paid' ? 'blue' : 'amber'}>{a.audience}</StatusBadge>
      ),
    },
    {
      key: 'enabled',
      header: 'Enabled',
      render: (a) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onToggle(a);
          }}
          className={`inline-flex h-5 w-9 items-center rounded-full transition ${a.enabled ? 'bg-green-500' : 'bg-gray-300'}`}
          aria-pressed={a.enabled}
          aria-label={a.enabled ? 'Disable announcement' : 'Enable announcement'}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${a.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      ),
    },
    {
      key: 'window',
      header: 'Window',
      render: (a) => (
        <span className="text-xs text-gray-600">
          {a.startsAt ? dayjs(a.startsAt).format('YYYY-MM-DD') : 'open'}
          {' → '}
          {a.endsAt ? dayjs(a.endsAt).format('YYYY-MM-DD') : 'open'}
        </span>
      ),
    },
    { key: 'createdBy', header: 'By', render: (a) => <span className="text-xs text-gray-600">{a.createdBy || '—'}</span> },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (a) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setDeleting(a);
          }}
          className="text-xs text-red-600 hover:underline"
        >
          Delete
        </button>
      ),
    },
  ];

  return (
    <div>
      <AdminPageHeader
        title="System announcements"
        subtitle={`${total} total`}
        actions={
          <button
            onClick={() => router.push('/admin/announcements/new')}
            className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800"
          >
            New announcement
          </button>
        }
      />

      <AdminTable<Announcement>
        columns={columns}
        rows={items}
        isLoading={isLoading}
        emptyMessage="No announcements yet"
        onRowClick={(a) => router.push(`/admin/announcements/${a.id || a._id}`)}
      />

      <ConfirmDialog
        open={!!deleting}
        title="Delete announcement"
        description={`This will permanently remove "${deleting?.title}".`}
        tone="danger"
        confirmLabel="Delete"
        busy={busy}
        onConfirm={onDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
