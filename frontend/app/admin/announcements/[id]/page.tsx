// frontend/app/admin/announcements/[id]/page.tsx

'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import useSWR from 'swr';
import dayjs from 'dayjs';
import AdminApi from '@/lib/admin/api';
import AdminPageHeader from '../../_components/AdminPageHeader';
import AnnouncementForm from '../_components/AnnouncementForm';

type Announcement = {
  id: string;
  _id: string;
  title: string;
  content: string;
  audience: 'all' | 'free' | 'paid';
  enabled: boolean;
  startsAt?: string;
  endsAt?: string;
};

// Convert ISO date string into the value format expected by <input type="datetime-local">.
// datetime-local needs 'YYYY-MM-DDTHH:mm', no timezone.
const toLocalInput = (iso?: string) => (iso ? dayjs(iso).format('YYYY-MM-DDTHH:mm') : '');

export default function AdminAnnouncementEditPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const { data, isLoading } = useSWR(
    id ? ['/api/admin/announcements/get', { id }] : null,
    AdminApi.fetcher
  );
  const a = (data as any)?.data as Announcement | undefined;

  if (!id) return null;
  if (isLoading) return <div className="p-4 text-gray-500">Loading…</div>;
  if (!a) return <div className="p-4 text-gray-500">Announcement not found.</div>;

  return (
    <div>
      <AdminPageHeader title="Edit announcement" subtitle={a.title} />
      <AnnouncementForm
        mode="update"
        initial={{
          id: a.id,
          title: a.title,
          content: a.content,
          audience: a.audience,
          enabled: a.enabled,
          startsAt: toLocalInput(a.startsAt),
          endsAt: toLocalInput(a.endsAt),
        }}
      />
    </div>
  );
}
