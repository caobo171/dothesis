// frontend/app/admin/_components/JobListPage.tsx
//
// Generic list page used by the four job sections (humanize, plagiarism,
// autocite, documents). Each section provides its own columns and (optionally)
// the set of statuses for the dropdown. The list URL and a section title are
// configurable.
//
// Why a shared page rather than four near-identical pages: the only thing that
// varies per section is column rendering. Filters, pagination, owner lookup,
// and table layout are 1:1.

'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import dayjs from 'dayjs';
import Link from 'next/link';
import AdminPageHeader from './AdminPageHeader';
import AdminTable, { Column } from './AdminTable';
import Pagination from './Pagination';
import StatusBadge from './StatusBadge';
import useAdminList from './useAdminList';

export type JobBase = {
  id: string;
  _id: string;
  owner: string;
  status?: string;
  createdAt: string;
  ownerInfo: { email: string; username: string } | null;
};

type Props<T extends JobBase> = {
  title: string;
  // Endpoint, e.g. '/api/admin/humanize'.
  url: string;
  // Detail-page route prefix, e.g. '/admin/humanize'. Detail href is `${prefix}/${row.id}`.
  detailHrefPrefix: string;
  // Column definitions specific to the section. Keep them between the
  // built-in `time` and `owner` columns by spreading at the front of the array.
  extraColumns: Column<T>[];
  // Status options for the filter dropdown. If empty/undefined, the dropdown is hidden.
  statuses?: string[];
  // Show/hide the q-search input.
  showSearch?: boolean;
  searchPlaceholder?: string;
};

export function JobListPage<T extends JobBase>({
  title,
  url,
  detailHrefPrefix,
  extraColumns,
  statuses,
  showSearch = true,
  searchPlaceholder = 'Search…',
}: Props<T>) {
  const router = useRouter();

  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [owner, setOwner] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  const params: Record<string, any> = { page, limit: 25 };
  if (q.trim()) params.q = q.trim();
  if (status) params.status = status;
  if (owner.trim()) params.owner = owner.trim();
  if (dateFrom) params.dateFrom = dateFrom;
  if (dateTo) params.dateTo = dateTo;

  const { items, total, isLoading } = useAdminList<T>(url, params);

  const onFilterChange = (cb: () => void) => {
    setPage(1);
    cb();
  };

  const columns: Column<T>[] = [
    {
      key: 'createdAt',
      header: 'Time',
      render: (r) => <span className="text-gray-600">{dayjs(r.createdAt).format('YYYY-MM-DD HH:mm')}</span>,
    },
    {
      key: 'owner',
      header: 'Owner',
      render: (r) =>
        r.ownerInfo ? (
          <Link
            href={`/admin/users/${r.owner}`}
            className="text-gray-900 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {r.ownerInfo.email}
          </Link>
        ) : (
          <span className="font-mono text-xs text-gray-500">{r.owner}</span>
        ),
    },
    ...extraColumns,
  ];

  return (
    <div>
      <AdminPageHeader title={title} subtitle={`${total} total`} />

      <div className="mb-4 grid grid-cols-1 gap-2 rounded-lg border border-gray-200 bg-white p-3 sm:grid-cols-6">
        {showSearch && (
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={q}
            onChange={(e) => onFilterChange(() => setQ(e.target.value))}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm sm:col-span-2"
          />
        )}
        <input
          type="text"
          placeholder="Owner ID"
          value={owner}
          onChange={(e) => onFilterChange(() => setOwner(e.target.value))}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        {statuses && statuses.length > 0 && (
          <select
            value={status}
            onChange={(e) => onFilterChange(() => setStatus(e.target.value))}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="">Any status</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
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

      <AdminTable<T>
        columns={columns}
        rows={items}
        isLoading={isLoading}
        emptyMessage="No results"
        onRowClick={(r) => router.push(`${detailHrefPrefix}/${r.id || r._id}`)}
      />

      <Pagination page={page} limit={25} total={total} onChange={setPage} />
    </div>
  );
}

// Status badge tone mapping shared across sections.
export function statusTone(status?: string) {
  if (!status) return 'gray' as const;
  if (status === 'completed' || status === 'done' || status === 'success') return 'green' as const;
  if (status === 'failed' || status === 'cancelled') return 'red' as const;
  if (status === 'processing') return 'blue' as const;
  if (status === 'pending') return 'yellow' as const;
  return 'gray' as const;
}

export function renderStatus(status?: string) {
  if (!status) return <StatusBadge tone="gray">—</StatusBadge>;
  return <StatusBadge tone={statusTone(status)}>{status}</StatusBadge>;
}

export default JobListPage;
