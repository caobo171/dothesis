// frontend/app/admin/users/[id]/page.tsx
//
// Admin user detail page. Shows profile, computed counts, credit totals,
// and offers admin actions: add credit, change plan/role, deactivate/activate.
//
// All mutations confirmed via ConfirmDialog. Mutations call the corresponding
// admin endpoint, then re-fetch the detail via SWR mutate.

'use client';

import React, { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import AdminApi from '@/lib/admin/api';
import { useMe } from '@/hooks/user';
import AdminPageHeader from '../../_components/AdminPageHeader';
import StatusBadge from '../../_components/StatusBadge';
import ConfirmDialog from '../../_components/ConfirmDialog';

type UserDetail = {
  id: string;
  _id: string;
  username: string;
  fullName: string;
  email: string;
  role: string;
  plan: string;
  credit: number;
  emailVerified: boolean;
  disabled?: boolean;
  is_admin?: boolean;
  is_super_admin?: boolean;
  createdAt: string;
  updatedAt: string;
  lastLogin?: string;
  counts?: {
    documents: number;
    humanize: number;
    plagiarism: number;
    autocite: number;
  };
  creditTotals?: {
    inbound: number;
    outbound: number;
  };
};

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;

  const { data: me } = useMe();
  const isSuperAdmin = !!me?.is_super_admin;

  // Detail fetch — passing AdminApi.fetcher explicitly per project convention.
  const { data, mutate, isLoading } = useSWR(
    id ? ['/api/admin/users/get', { id }] : null,
    AdminApi.fetcher
  );
  const user = (data as any)?.data as UserDetail | undefined;

  // Inline form state for the add-credit modal.
  const [addCreditOpen, setAddCreditOpen] = useState(false);
  const [addAmount, setAddAmount] = useState('10');
  const [addNote, setAddNote] = useState('');
  const [busy, setBusy] = useState(false);

  // Pending confirm-dialog actions (deactivate / activate / role changes).
  const [confirm, setConfirm] = useState<
    | { kind: 'deactivate' }
    | { kind: 'activate' }
    | { kind: 'role'; role: 'User' | 'Admin' }
    | { kind: 'plan'; plan: string }
    | null
  >(null);

  if (!id) return null;
  if (isLoading) return <div className="p-4 text-gray-500">Loading…</div>;
  if (!user) return <div className="p-4 text-gray-500">User not found.</div>;

  const callAddCredit = async () => {
    const amount = Number(addAmount);
    if (!amount || amount <= 0) {
      toast.error('Amount must be > 0');
      return;
    }
    setBusy(true);
    try {
      const res = await AdminApi.post('/api/admin/users/credit', {
        id,
        amount,
        description: addNote || undefined,
      });
      if (res.code !== 1) {
        toast.error(res.message || 'Failed to add credit');
        return;
      }
      toast.success(`Added ${amount} credits`);
      setAddCreditOpen(false);
      setAddNote('');
      await mutate();
    } finally {
      setBusy(false);
    }
  };

  const callConfirmAction = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      let url = '';
      let payload: Record<string, any> = { id };
      if (confirm.kind === 'deactivate') url = '/api/admin/users/deactivate';
      else if (confirm.kind === 'activate') url = '/api/admin/users/activate';
      else if (confirm.kind === 'role') {
        url = '/api/admin/users/role';
        payload.role = confirm.role;
      } else if (confirm.kind === 'plan') {
        url = '/api/admin/users/plan';
        payload.plan = confirm.plan;
      }
      const res = await AdminApi.post(url, payload);
      if (res.code !== 1) {
        toast.error(res.message || 'Action failed');
        return;
      }
      toast.success('Updated');
      setConfirm(null);
      await mutate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <AdminPageHeader
        title={user.fullName || user.email}
        subtitle={user.email}
        actions={
          <>
            <button
              onClick={() => router.back()}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              Back
            </button>
            <button
              onClick={() => setAddCreditOpen(true)}
              className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800"
            >
              Add credit
            </button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Profile card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Profile</div>
          <dl className="space-y-2 text-sm">
            <Row k="Username" v={user.username} />
            <Row k="Full name" v={user.fullName} />
            <Row k="Email" v={user.email} />
            <Row k="Verified" v={user.emailVerified ? <StatusBadge tone="green">yes</StatusBadge> : <StatusBadge tone="yellow">no</StatusBadge>} />
            <Row k="Status" v={user.disabled ? <StatusBadge tone="red">disabled</StatusBadge> : <StatusBadge tone="green">active</StatusBadge>} />
            <Row k="Joined" v={dayjs(user.createdAt).format('YYYY-MM-DD HH:mm')} />
            {user.lastLogin && <Row k="Last login" v={dayjs(user.lastLogin).format('YYYY-MM-DD HH:mm')} />}
          </dl>
        </div>

        {/* Plan / Role / Credit */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Account</div>
          <dl className="space-y-3 text-sm">
            <Row
              k="Role"
              v={
                <div className="flex items-center gap-2">
                  <StatusBadge tone={user.role === 'Admin' ? 'amber' : 'gray'}>{user.role}</StatusBadge>
                  {user.is_super_admin && <StatusBadge tone="amber">SUPER</StatusBadge>}
                  {isSuperAdmin && (
                    <select
                      value={user.role}
                      onChange={(e) =>
                        setConfirm({ kind: 'role', role: e.target.value as 'User' | 'Admin' })
                      }
                      className="ml-auto rounded border border-gray-300 px-2 py-0.5 text-xs"
                    >
                      <option value="User">User</option>
                      <option value="Admin">Admin</option>
                    </select>
                  )}
                </div>
              }
            />
            <Row
              k="Plan"
              v={
                <div className="flex items-center gap-2">
                  <StatusBadge tone={user.plan === 'free' ? 'gray' : 'blue'}>{user.plan}</StatusBadge>
                  <select
                    value={user.plan}
                    onChange={(e) => setConfirm({ kind: 'plan', plan: e.target.value })}
                    className="ml-auto rounded border border-gray-300 px-2 py-0.5 text-xs"
                  >
                    <option value="free">free</option>
                    <option value="pro">pro</option>
                  </select>
                </div>
              }
            />
            <Row k="Current credit" v={<span className="font-mono">{user.credit}</span>} />
            {user.creditTotals && (
              <>
                <Row k="Total inbound" v={<span className="font-mono text-green-700">+{user.creditTotals.inbound}</span>} />
                <Row k="Total outbound" v={<span className="font-mono text-red-700">-{user.creditTotals.outbound}</span>} />
              </>
            )}
          </dl>

          {/* Deactivate / activate (super admin only) */}
          {isSuperAdmin && (
            <div className="mt-4 border-t border-gray-100 pt-4">
              {user.disabled ? (
                <button
                  onClick={() => setConfirm({ kind: 'activate' })}
                  className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                >
                  Re-activate user
                </button>
              ) : (
                <button
                  onClick={() => setConfirm({ kind: 'deactivate' })}
                  className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
                >
                  Deactivate user
                </button>
              )}
            </div>
          )}
        </div>

        {/* Counts */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 text-xs uppercase tracking-wider text-gray-500">Activity</div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Stat k="Documents" v={user.counts?.documents ?? 0} />
            <Stat k="Humanize" v={user.counts?.humanize ?? 0} />
            <Stat k="Plagiarism" v={user.counts?.plagiarism ?? 0} />
            <Stat k="AutoCite" v={user.counts?.autocite ?? 0} />
          </dl>
        </div>
      </div>

      {/* Add credit modal */}
      <ConfirmDialog
        open={addCreditOpen}
        title="Add credit"
        description={
          <div className="space-y-3">
            <p>Grant credits to {user.email}. Recorded as an inbound transaction with orderType <code>admin_grant</code>.</p>
            <div>
              <label className="block text-xs font-medium text-gray-600">Amount</label>
              <input
                type="number"
                min={1}
                value={addAmount}
                onChange={(e) => setAddAmount(e.target.value)}
                className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600">Note (optional)</label>
              <input
                type="text"
                value={addNote}
                onChange={(e) => setAddNote(e.target.value)}
                placeholder="Reason for grant"
                className="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
              />
            </div>
          </div>
        }
        confirmLabel={`Grant ${addAmount || 0} credits`}
        busy={busy}
        onConfirm={callAddCredit}
        onClose={() => setAddCreditOpen(false)}
      />

      {/* Generic action confirm */}
      <ConfirmDialog
        open={!!confirm}
        title={
          confirm?.kind === 'deactivate'
            ? 'Deactivate user'
            : confirm?.kind === 'activate'
              ? 'Re-activate user'
              : confirm?.kind === 'role'
                ? `Change role to ${confirm.role}`
                : confirm?.kind === 'plan'
                  ? `Change plan to ${confirm.plan}`
                  : ''
        }
        description={
          confirm?.kind === 'deactivate'
            ? 'The user will be marked disabled. Existing JWTs remain valid until expiry.'
            : confirm?.kind === 'activate'
              ? 'The user will be marked active.'
              : 'This will update the user immediately.'
        }
        tone={confirm?.kind === 'deactivate' ? 'danger' : 'primary'}
        confirmLabel="Apply"
        busy={busy}
        onConfirm={callConfirmAction}
        onClose={() => setConfirm(null)}
      />
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-xs uppercase tracking-wider text-gray-500">{k}</dt>
      <dd className="text-right text-gray-900">{v}</dd>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: number }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-500">{k}</div>
      <div className="text-lg font-semibold text-gray-900">{v}</div>
    </div>
  );
}
