'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Sidebar } from '@/components/layout/Sidebar';
import { Topbar } from '@/components/layout/Topbar';
import { ClientOnly } from '@/components/common/ClientOnly';
import { useMe } from '@/hooks/user';
import Cookie from '@/lib/core/fetch/Cookie';
import { useEffect } from 'react';

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (!isLoading && !user && !Cookie.fromDocument('access_token')) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  return (
    <ClientOnly>
      <div className="min-h-screen bg-bg-soft">
        <Sidebar />
        <div className="ml-64">
          <Topbar />
          <main className="p-6">{children}</main>
        </div>
      </div>
    </ClientOnly>
  );
}
