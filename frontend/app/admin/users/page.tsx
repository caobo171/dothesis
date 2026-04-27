// frontend/app/admin/users/page.tsx
//
// Admin user list. Filters: q (search), role, plan, emailVerified, disabled.
// Pagination via Pagination component, default 25 per page.

'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import dayjs from 'dayjs';
import AdminPageHeader from '../_components/AdminPageHeader';
import AdminTable, { Column } from '../_components/AdminTable';
import Pagination from '../_components/Pagination';
import StatusBadge from '../_components/StatusBadge';
import useAdminList from '../_components/useAdminList';

type UserRow = {
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
};

export default function AdminUsersPage() {
  const router = useRouter();

  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [plan, setPlan] = useState('');
  const [verifiedFilter, setVerifiedFilter] = useState<'' | 'true' | 'false'>('');
  const [disabledFilter, setDisabledFilter] = useState<'' | 'true' | 'false'>('');
  const [page, setPage] = useState(1);

  // Single object collected for the SWR key. Empty/falsy fields are excluded
  // so SWR doesn't churn on every keystroke into an empty filter input.
  const params: Record<string, any> = { page, limit: 25 };
  if (q.trim()) params.q = q.trim();
  if (role) params.role = role;
  if (plan) params.plan = plan;
  if (verifiedFilter) params.emailVerified = verifiedFilter;
  if (disabledFilter) params.disabled = disabledFilter;

  const { items, total, isLoading } = useAdminList<UserRow>('/api/admin/users', params);

  const columns: Column<UserRow>[] = [
    {
      key: 'email',
      header: 'Email',
      render: (u) => (
        <div>
          <div className="font-medium text-gray-900">{u.email}</div>
          <div className="text-xs text-gray-500">{u.fullName}</div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      render: (u) => (
        <div className="flex items-center gap-1">
          <StatusBadge tone={u.role === 'Admin' ? 'amber' : 'gray'}>{u.role}</StatusBadge>
          {u.is_super_admin && <StatusBadge tone="amber">SUPER</StatusBadge>}
        </div>
      ),
    },
    { key: 'plan', header: 'Plan', render: (u) => <StatusBadge tone={u.plan === 'free' ? 'gray' : 'blue'}>{u.plan}</StatusBadge> },
    { key: 'credit', header: 'Credit', render: (u) => <span className="font-mono">{u.credit}</span> },
    {
      key: 'verified',
      header: 'Verified',
      render: (u) =>
        u.emailVerified ? <StatusBadge tone="green">yes</StatusBadge> : <StatusBadge tone="yellow">no</StatusBadge>,
    },
    {
      key: 'disabled',
      header: 'Status',
      render: (u) => (u.disabled ? <StatusBadge tone="red">disabled</StatusBadge> : <StatusBadge tone="green">active</StatusBadge>),
    },
    { key: 'createdAt', header: 'Joined', render: (u) => <span className="text-gray-600">{dayjs(u.createdAt).format('YYYY-MM-DD')}</span> },
  ];

  // Reset page when filters change so the user isn't stranded on a non-existent page.
  const onFilterChange = (cb: () => void) => {
    setPage(1);
    cb();
  };

  return (
    <div>
      <AdminPageHeader title="Users" subtitle={`${total} total`} />

      <div className="mb-4 grid grid-cols-1 gap-2 rounded-lg border border-gray-200 bg-white p-3 sm:grid-cols-6">
        <input
          type="text"
          placeholder="Search email / name / username"
          value={q}
          onChange={(e) => onFilterChange(() => setQ(e.target.value))}
          className="col-span-2 rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        <select
          value={role}
          onChange={(e) => onFilterChange(() => setRole(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any role</option>
          <option value="User">User</option>
          <option value="Admin">Admin</option>
        </select>
        <select
          value={plan}
          onChange={(e) => onFilterChange(() => setPlan(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any plan</option>
          <option value="free">free</option>
          <option value="pro">pro</option>
        </select>
        <select
          value={verifiedFilter}
          onChange={(e) => onFilterChange(() => setVerifiedFilter(e.target.value as any))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any verified</option>
          <option value="true">Verified</option>
          <option value="false">Unverified</option>
        </select>
        <select
          value={disabledFilter}
          onChange={(e) => onFilterChange(() => setDisabledFilter(e.target.value as any))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any status</option>
          <option value="false">Active</option>
          <option value="true">Disabled</option>
        </select>
      </div>

      <AdminTable<UserRow>
        columns={columns}
        rows={items}
        isLoading={isLoading}
        emptyMessage="No users match these filters"
        onRowClick={(u) => router.push(`/admin/users/${u.id || u._id}`)}
      />

      <Pagination page={page} limit={25} total={total} onChange={setPage} />
    </div>
  );
}
