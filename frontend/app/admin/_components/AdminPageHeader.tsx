// frontend/app/admin/_components/AdminPageHeader.tsx
//
// Shared header for admin pages. Title plus optional subtitle and right-aligned
// actions slot. Centralizes typography so individual sections don't drift.

'use client';

import React from 'react';

type Props = {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
};

export function AdminPageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export default AdminPageHeader;
