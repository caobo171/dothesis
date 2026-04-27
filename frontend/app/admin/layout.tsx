// frontend/app/admin/layout.tsx
//
// Root of the /admin route group. Single source of truth for the client-side gate.
// Real enforcement is server-side per route — this is UX only.
//
// Gate has two phases:
//  1. Synchronous: if there is no access_token cookie, redirect to /login immediately.
//     We can't wait for useMe() because SWR never resolves with a null key, so isLoading
//     would be permanently true and the user would see a blank page.
//  2. Async: once we have a token, wait for useMe() to populate, then redirect non-admins.

'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMe } from '@/hooks/user';
import Cookie from '@/lib/core/fetch/Cookie';
import AdminSidebar from './_components/AdminSidebar';
import AdminTopbar from './_components/AdminTopbar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hasToken = typeof window !== 'undefined' && !!Cookie.fromDocument('access_token');
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    // Phase 1: no cookie → push to login. useMe() never resolves in this case
    // (SWR key is null), so we must redirect from here, not wait on isLoading.
    if (typeof window !== 'undefined' && !hasToken) {
      router.replace('/login');
      return;
    }

    // Phase 2: signed in but not admin → bounce to home.
    if (!isLoading && user && !user.is_admin) {
      router.replace('/');
    }
  }, [hasToken, user, isLoading, router]);

  // Render nothing while:
  //  - we have no token (waiting for the redirect to /login)
  //  - we have a token but useMe() is still loading
  //  - the user resolved but is not an admin (waiting for the redirect to /)
  if (!hasToken || isLoading || !user || !user.is_admin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminSidebar isSuperAdmin={!!user.is_super_admin} />
      <div className="ml-60">
        <AdminTopbar email={user.email} isSuperAdmin={!!user.is_super_admin} />
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
