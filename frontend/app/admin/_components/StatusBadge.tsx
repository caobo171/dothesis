// frontend/app/admin/_components/StatusBadge.tsx
//
// Small color-coded chip for statuses. Centralized so section pages share the
// same color vocabulary (e.g., "completed" is always green).

'use client';

import React from 'react';

type Tone = 'green' | 'yellow' | 'red' | 'gray' | 'blue' | 'amber';

type Props = {
  tone?: Tone;
  children: React.ReactNode;
  title?: string;
};

const TONE_CLASS: Record<Tone, string> = {
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-yellow-100 text-yellow-800',
  red: 'bg-red-100 text-red-800',
  gray: 'bg-gray-100 text-gray-700',
  blue: 'bg-blue-100 text-blue-800',
  amber: 'bg-amber-100 text-amber-800',
};

export function StatusBadge({ tone = 'gray', children, title }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
      title={title}
    >
      {children}
    </span>
  );
}

export default StatusBadge;
