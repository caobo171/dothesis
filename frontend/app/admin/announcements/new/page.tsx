// frontend/app/admin/announcements/new/page.tsx

'use client';

import React from 'react';
import AdminPageHeader from '../../_components/AdminPageHeader';
import AnnouncementForm from '../_components/AnnouncementForm';

export default function AdminAnnouncementNewPage() {
  return (
    <div>
      <AdminPageHeader title="New announcement" />
      <AnnouncementForm
        mode="create"
        initial={{
          title: '',
          content: '',
          audience: 'all',
          enabled: false,
        }}
      />
    </div>
  );
}
