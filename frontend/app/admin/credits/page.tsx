// frontend/app/admin/credits/page.tsx
//
// Admin credit transactions list. Read-only view of every transaction across
// the platform. Mutations only happen via /admin/users/credit (the per-user
// "add credit" action from slice 2).

'use client';

import React, { useState } from 'react';
import dayjs from 'dayjs';
import Link from 'next/link';
import AdminPageHeader from '../_components/AdminPageHeader';
import AdminTable, { Column } from '../_components/AdminTable';
import Pagination from '../_components/Pagination';
import StatusBadge from '../_components/StatusBadge';
import useAdminList from '../_components/useAdminList';

type CreditRow = {
  id: string;
  _id: string;
  amount: number;
  direction: 'inbound' | 'outbound';
  owner: string;
  status: string;
  description?: string;
  orderType?: string;
  orderId?: string;
  createdAt: string;
  ownerInfo: { email: string; username: string } | null;
};

export default function AdminCreditsPage() {
  const [direction, setDirection] = useState<'' | 'inbound' | 'outbound'>('');
  const [status, setStatus] = useState('');
  const [orderType, setOrderType] = useState('');
  const [owner, setOwner] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  const params: Record<string, any> = { page, limit: 25 };
  if (direction) params.direction = direction;
  if (status) params.status = status;
  if (orderType) params.orderType = orderType;
  if (owner.trim()) params.owner = owner.trim();
  if (dateFrom) params.dateFrom = dateFrom;
  if (dateTo) params.dateTo = dateTo;

  const { items, total, isLoading } = useAdminList<CreditRow>('/api/admin/credits', params);

  const onFilterChange = (cb: () => void) => {
    setPage(1);
    cb();
  };

  const columns: Column<CreditRow>[] = [
    { key: 'createdAt', header: 'Time', render: (r) => <span className="text-gray-600">{dayjs(r.createdAt).format('YYYY-MM-DD HH:mm')}</span> },
    {
      key: 'owner',
      header: 'Owner',
      render: (r) =>
        r.ownerInfo ? (
          <Link href={`/admin/users/${r.owner}`} className="text-gray-900 hover:underline">
            {r.ownerInfo.email}
          </Link>
        ) : (
          <span className="font-mono text-xs text-gray-500">{r.owner}</span>
        ),
    },
    {
      key: 'direction',
      header: 'Direction',
      render: (r) => (
        <StatusBadge tone={r.direction === 'inbound' ? 'green' : 'red'}>{r.direction}</StatusBadge>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      render: (r) => (
        <span className={`font-mono ${r.direction === 'inbound' ? 'text-green-700' : 'text-red-700'}`}>
          {r.direction === 'inbound' ? '+' : '-'}
          {r.amount}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <StatusBadge tone={r.status === 'completed' || r.status === 'success' ? 'green' : r.status === 'failed' ? 'red' : 'yellow'}>
          {r.status}
        </StatusBadge>
      ),
    },
    { key: 'orderType', header: 'Source', render: (r) => <span className="text-gray-700">{r.orderType || '—'}</span> },
    { key: 'description', header: 'Note', render: (r) => <span className="text-gray-600">{r.description || ''}</span> },
  ];

  return (
    <div>
      <AdminPageHeader title="Credit transactions" subtitle={`${total} total`} />

      <div className="mb-4 grid grid-cols-1 gap-2 rounded-lg border border-gray-200 bg-white p-3 sm:grid-cols-6">
        <input
          type="text"
          placeholder="Owner ID"
          value={owner}
          onChange={(e) => onFilterChange(() => setOwner(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm sm:col-span-2"
        />
        <select
          value={direction}
          onChange={(e) => onFilterChange(() => setDirection(e.target.value as any))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any direction</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
        </select>
        <select
          value={status}
          onChange={(e) => onFilterChange(() => setStatus(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any status</option>
          <option value="completed">completed</option>
          <option value="success">success</option>
          <option value="pending">pending</option>
          <option value="failed">failed</option>
        </select>
        <select
          value={orderType}
          onChange={(e) => onFilterChange(() => setOrderType(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">Any source</option>
          <option value="admin_grant">admin_grant</option>
          <option value="purchase">purchase</option>
          <option value="humanize">humanize</option>
          <option value="autocite">autocite</option>
          <option value="plagiarism">plagiarism</option>
        </select>
        <div />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onFilterChange(() => setDateFrom(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onFilterChange(() => setDateTo(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>

      <AdminTable<CreditRow>
        columns={columns}
        rows={items}
        isLoading={isLoading}
        emptyMessage="No transactions match these filters"
      />

      <Pagination page={page} limit={25} total={total} onChange={setPage} />
    </div>
  );
}
