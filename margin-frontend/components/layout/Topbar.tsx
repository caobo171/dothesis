'use client';

import { usePathname } from 'next/navigation';
import { CreditPill } from '@/components/ui/CreditPill';

const TITLES: Record<string, string> = {
  '/humanizer': 'Humanizer',
  '/auto-cite': 'Auto-Cite',
  '/library': 'Library',
  '/history': 'History',
};

export function Topbar() {
  const pathname = usePathname();
  const title = TITLES[pathname] || 'Margin';

  return (
    <header className="h-[58px] border-b border-rule bg-white flex items-center justify-between px-6">
      <h1 className="text-sm font-semibold text-ink">{title}</h1>
      <div className="flex items-center gap-3">
        <CreditPill />
      </div>
    </header>
  );
}
