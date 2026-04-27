// frontend/app/admin/_components/JobDetailFrame.tsx
//
// Shared frame for job-detail pages. Handles SWR fetching, loading/empty
// states, the back button, owner link, and the cancel/delete action buttons.
// Section-specific content goes in the children render-prop.

'use client';

import React, { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import dayjs from 'dayjs';
import { toast } from 'react-toastify';
import AdminApi from '@/lib/admin/api';
import { useMe } from '@/hooks/user';
import AdminPageHeader from './AdminPageHeader';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import { statusTone } from './JobListPage';

export type JobDetailBase = {
  id: string;
  _id: string;
  owner: string;
  status?: string;
  createdAt: string;
  updatedAt?: string;
  ownerInfo: { email: string; username: string } | null;
};

type Props<T extends JobDetailBase> = {
  // Section URL roots. Examples for humanize:
  //   detailUrl: '/api/admin/humanize/get'
  //   cancelUrl: '/api/admin/humanize/cancel' (omit if not cancellable)
  //   deleteUrl: '/api/admin/humanize/delete'
  //   listHref: '/admin/humanize'
  //   title: e.g. 'Humanize job'
  detailUrl: string;
  cancelUrl?: string;
  deleteUrl: string;
  listHref: string;
  title: string;
  renderBody: (job: T) => React.ReactNode;
};

export function JobDetailFrame<T extends JobDetailBase>(props: Props<T>) {
  const { detailUrl, cancelUrl, deleteUrl, listHref, title, renderBody } = props;
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;
  const { data: me } = useMe();
  const isSuperAdmin = !!me?.is_super_admin;

  const { data, mutate, isLoading } = useSWR(
    id ? [detailUrl, { id }] : null,
    AdminApi.fetcher
  );
  const job = (data as any)?.data as T | undefined;

  const [confirm, setConfirm] = useState<'cancel' | 'delete' | null>(null);
  const [busy, setBusy] = useState(false);

  if (!id) return null;
  if (isLoading) return <div className="p-4 text-gray-500">Loading…</div>;
  if (!job) return <div className="p-4 text-gray-500">Not found.</div>;

  const callAction = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      const url = confirm === 'cancel' ? cancelUrl : deleteUrl;
      if (!url) {
        toast.error('Action not available');
        return;
      }
      const res = await AdminApi.post(url, { id });
      if (res.code !== 1) {
        toast.error(res.message || 'Action failed');
        return;
      }
      toast.success(confirm === 'delete' ? 'Deleted' : 'Cancelled');
      if (confirm === 'delete') {
        router.push(listHref);
      } else {
        setConfirm(null);
        await mutate();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <AdminPageHeader
        title={title}
        subtitle={`${dayjs(job.createdAt).format('YYYY-MM-DD HH:mm')} · ${job.id}`}
        actions={
          <>
            <Link
              href={listHref}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              Back
            </Link>
            {cancelUrl && job.status && job.status !== 'cancelled' && job.status !== 'completed' && job.status !== 'done' && (
              <button
                onClick={() => setConfirm('cancel')}
                className="rounded border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800 hover:bg-amber-100"
              >
                Cancel job
              </button>
            )}
            {isSuperAdmin && (
              <button
                onClick={() => setConfirm('delete')}
                className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              >
                Delete
              </button>
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <div>
          <span className="text-xs uppercase tracking-wider text-gray-500">Owner: </span>
          {job.ownerInfo ? (
            <Link href={`/admin/users/${job.owner}`} className="text-gray-900 hover:underline">
              {job.ownerInfo.email}
            </Link>
          ) : (
            <span className="font-mono text-xs text-gray-500">{job.owner}</span>
          )}
        </div>
        {job.status && (
          <div>
            <span className="text-xs uppercase tracking-wider text-gray-500">Status: </span>
            <StatusBadge tone={statusTone(job.status)}>{job.status}</StatusBadge>
          </div>
        )}
        {job.updatedAt && (
          <div className="text-gray-500">Updated {dayjs(job.updatedAt).format('YYYY-MM-DD HH:mm')}</div>
        )}
      </div>

      {renderBody(job)}

      <ConfirmDialog
        open={!!confirm}
        title={confirm === 'delete' ? 'Delete record' : 'Cancel job'}
        description={
          confirm === 'delete'
            ? 'This permanently removes the record. The user keeps any credits already debited or refunded.'
            : 'Sets status to "cancelled". This is a soft cancel — any in-flight work in the queue will continue until it sees the new status.'
        }
        tone={confirm === 'delete' ? 'danger' : 'primary'}
        confirmLabel={confirm === 'delete' ? 'Delete' : 'Cancel job'}
        busy={busy}
        onConfirm={callAction}
        onClose={() => setConfirm(null)}
      />
    </div>
  );
}

export default JobDetailFrame;
