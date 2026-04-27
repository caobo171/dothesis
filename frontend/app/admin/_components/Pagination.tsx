// frontend/app/admin/_components/Pagination.tsx
//
// Lightweight pagination control — calls back into the parent rather than
// owning URL state itself, so each section can decide whether to sync to URL
// or keep paging local.

'use client';

import React from 'react';

type Props = {
  page: number;
  limit: number;
  total: number;
  onChange: (page: number) => void;
};

export function Pagination({ page, limit, total, onChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : (page - 1) * limit + 1;
  const end = Math.min(total, page * limit);

  const prevDisabled = page <= 1;
  const nextDisabled = page >= totalPages;

  return (
    <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
      <div>
        {total === 0 ? '0 results' : `${start}–${end} of ${total}`}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={prevDisabled}
          onClick={() => onChange(page - 1)}
          className="rounded border border-gray-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50 hover:bg-gray-50"
        >
          Previous
        </button>
        <span>
          Page {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={nextDisabled}
          onClick={() => onChange(page + 1)}
          className="rounded border border-gray-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-50 hover:bg-gray-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export default Pagination;
