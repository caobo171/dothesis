// frontend/app/admin/_components/AdminTopbar.tsx

'use client';

import Link from 'next/link';

type Props = {
  email: string;
  isSuperAdmin: boolean;
};

export function AdminTopbar({ email, isSuperAdmin }: Props) {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div className="text-sm text-gray-500">Admin</div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-700">{email}</span>
        {isSuperAdmin && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            Super admin
          </span>
        )}
        <Link
          href="/"
          className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-50"
        >
          Back to app
        </Link>
      </div>
    </header>
  );
}

export default AdminTopbar;
