// frontend/components/layout/AnnouncementBanner.tsx
//
// Renders enabled-and-current announcements at the top of the workspace.
// Cached by SWR so navigation between workspace pages doesn't refetch.
// Each banner is dismissable for the current session (sessionStorage).

'use client';

import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import Cookie from '@/lib/core/fetch/Cookie';
import Fetch from '@/lib/core/fetch/Fetch';

type Announcement = {
  id: string;
  _id: string;
  title: string;
  content: string;
  audience: string;
};

const fetcher = async (key: [string, Record<string, any>]) => {
  const [url, params] = key;
  const res = await Fetch.post(url, { ...params, access_token: Cookie.fromDocument('access_token') });
  return res.data as { code: number; data?: Announcement[] };
};

const DISMISSED_KEY = 'dothesis.dismissedAnnouncements';

const readDismissed = (): string[] => {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(sessionStorage.getItem(DISMISSED_KEY) || '[]');
  } catch {
    return [];
  }
};

const writeDismissed = (ids: string[]) => {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(ids));
};

export function AnnouncementBanner() {
  const hasToken = typeof window !== 'undefined' && !!Cookie.fromDocument('access_token');
  const { data } = useSWR(hasToken ? ['/api/announcements/active', {}] : null, fetcher, {
    // Don't hammer the endpoint — once per minute is plenty for a banner.
    refreshInterval: 60_000,
  });

  const [dismissed, setDismissed] = useState<string[]>([]);
  useEffect(() => {
    setDismissed(readDismissed());
  }, []);

  const list = (data?.data || []).filter((a) => !dismissed.includes(a.id || a._id));
  if (list.length === 0) return null;

  const dismiss = (id: string) => {
    const next = [...dismissed, id];
    setDismissed(next);
    writeDismissed(next);
  };

  return (
    <div className="space-y-2 px-6 pt-4">
      {list.map((a) => {
        const id = a.id || a._id;
        return (
          <div
            key={id}
            className="flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900"
            role="status"
          >
            <div>
              <div className="font-medium">{a.title}</div>
              {a.content && <div className="mt-0.5 whitespace-pre-wrap text-amber-800">{a.content}</div>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(id)}
              aria-label="Dismiss"
              className="ml-2 text-xs text-amber-700 hover:underline"
            >
              Dismiss
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default AnnouncementBanner;
