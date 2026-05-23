"use client";

import clsx from "clsx";
import type { ReactNode } from "react";

export type AdminColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
};

type AdminTableProps<T> = {
  columns: AdminColumn<T>[];
  rows: T[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onRowClick?: (row: T) => void;
  isLoading?: boolean;
  emptyMessage?: string;
};

export function AdminTable<T extends { id: string }>(props: AdminTableProps<T>) {
  const { columns, rows, total, page, pageSize, onPageChange, onRowClick, isLoading, emptyMessage } = props;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="overflow-hidden rounded-2xl border border-ink-100 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-ink-50">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={clsx("px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500", c.className)}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {isLoading && (
            <tr><td colSpan={columns.length} className="px-4 py-8 text-center text-ink-500">Loading…</td></tr>
          )}
          {!isLoading && rows.length === 0 && (
            <tr><td colSpan={columns.length} className="px-4 py-8 text-center text-ink-500">
              {emptyMessage || "No results"}
            </td></tr>
          )}
          {!isLoading && rows.map((row) => (
            <tr
              key={row.id}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={clsx(onRowClick && "cursor-pointer hover:bg-ink-50/60", "transition-colors")}
            >
              {columns.map((c) => (
                <td key={c.key} className={clsx("px-4 py-3 text-ink-900", c.className)}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center justify-between border-t border-ink-100 bg-white px-4 py-3 text-sm">
        <div className="text-ink-500">{total.toLocaleString()} total</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="rounded-md border border-ink-200 px-3 py-1 text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-ink-500">{page} / {totalPages}</span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="rounded-md border border-ink-200 px-3 py-1 text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
