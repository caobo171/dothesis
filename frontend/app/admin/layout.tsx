// frontend/app/admin/layout.tsx
//
// Root of the /admin route group. Single source of truth for the client-side gate.
// Real enforcement is server-side per route — this is UX only.

'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMe } from '@/hooks/user';
import Cookie from '@/lib/core/fetch/Cookie';
import { ClientOnly } from '@/components/common/ClientOnly';
import AdminSidebar from './_components/AdminSidebar';
import AdminTopbar from './_components/AdminTopbar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (isLoading) return;

    // Not signed in → push to login.
    if (!user && !Cookie.fromDocument('access_token')) {
      router.replace('/login');
      return;
    }

    // Signed in but not admin → bounce to home. Server-side gate would also reject,
    // but we don't even render the shell in this case.
    if (user && !user.is_admin) {
      router.replace('/');
    }
  }, [user, isLoading, router]);

  // Render nothing until we know the user is admin. Avoids flicker of the shell
  // before the redirect lands.
  if (isLoading || !user || !user.is_admin) {
    return null;
  }

  return (
    <ClientOnly>
      <div className="min-h-screen bg-gray-50">
        <AdminSidebar isSuperAdmin={!!user.is_super_admin} />
        <div className="ml-60">
          <AdminTopbar email={user.email} isSuperAdmin={!!user.is_super_admin} />
          <main className="p-6">{children}</main>
        </div>
      </div>
    </ClientOnly>
  );
}
