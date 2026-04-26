'use client';

import { useState } from 'react';
import { CiteBoard } from '@/components/cite/CiteBoard';
import { PlagiarismView } from '@/components/cite/PlagiarismView';
import { clsx } from 'clsx';

const TABS = [
  { value: 'cite', label: 'Auto-Cite' },
  { value: 'plagiarism', label: 'Plagiarism Check' },
];

export default function AutoCitePage() {
  const [tab, setTab] = useState('cite');

  return (
    <div>
      <div className="flex gap-1 mb-4 bg-white rounded-lg border border-rule p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx(
              'px-4 py-2 rounded-md text-sm font-medium transition',
              tab === t.value ? 'bg-primary text-white' : 'text-ink-soft hover:bg-bg-soft'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'cite' ? <CiteBoard /> : <PlagiarismView />}
    </div>
  );
}
