// frontend/app/admin/_components/AdminTable.tsx
//
// Generic admin table. Columns are declarative so each section can customize
// rendering without re-implementing layout, loading state, or empty state.

'use client';

import React from 'react';

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  // Returns the cell content for a row. If undefined, renders nothing.
  render: (row: T) => React.ReactNode;
  className?: string;
};

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  isLoading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  // Optional row key extractor. Defaults to row.id then row._id.
  getRowKey?: (row: T, index: number) => string;
};

export function AdminTable<T extends { id?: string; _id?: string }>(props: Props<T>) {
  const { columns, rows, isLoading, emptyMessage = 'No results', onRowClick, getRowKey } = props;

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={`px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-gray-600 ${c.className || ''}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {isLoading ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-500">
                Loading…
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, idx) => {
              const key = getRowKey ? getRowKey(row, idx) : row.id || row._id || String(idx);
              return (
                <tr
                  key={key}
                  className={onRowClick ? 'cursor-pointer hover:bg-gray-50' : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={`px-4 py-2.5 align-middle ${c.className || ''}`}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export default AdminTable;
