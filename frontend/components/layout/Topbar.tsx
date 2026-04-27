'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ChevronRight, MessageSquare, HelpCircle, Zap } from 'lucide-react';
import { useBalance } from '@/hooks/credit';

const TITLES: Record<string, string> = {
  '/humanizer': 'Humanizer',
  '/auto-cite': 'Auto-Cite',
  '/library': 'Library',
  '/history': 'History',
  '/credit': 'Credits',
};

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { balance } = useBalance();

  // Top-level breadcrumb derived from the current path. The first segment maps
  // to a friendly label via TITLES; deeper segments fall back to the slug.
  const segments = pathname.split('/').filter(Boolean);
  const lastSegment = segments[segments.length - 1] || '';
  const title = TITLES[`/${segments[0] || ''}`] || lastSegment.replace(/-/g, ' ');

  return (
    <header className="h-[60px] border-b border-rule bg-white flex items-center justify-between px-6">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm">
        <Link href="/humanizer" className="text-ink-muted hover:text-ink-soft transition">
          Workspace
        </Link>
        <ChevronRight className="w-4 h-4 text-ink-muted" />
        <span className="font-semibold text-ink capitalize">{title}</span>
      </nav>

      {/* Right cluster: Feedback / Help / Credits */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => router.push('/feedback')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rule text-sm text-ink-soft hover:bg-bg-soft transition"
        >
          <MessageSquare className="w-4 h-4" />
          Feedback
        </button>

        <Link
          href="/help"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rule text-sm text-ink-soft hover:bg-bg-soft transition"
        >
          <HelpCircle className="w-4 h-4" />
          Help
        </Link>

        {/* Credits pill — clicking goes to the dedicated /credit page where the
            buy-credit packages live. Replaced the inline buy popover so the
            full pricing UX has room to breathe. */}
        <Link
          href="/credit"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-blue text-primary hover:bg-primary/10 transition"
        >
          <Zap className="w-4 h-4 fill-current" />
          <span className="text-sm font-semibold font-mono">{balance.toLocaleString()}</span>
          <span className="text-sm">credits</span>
        </Link>
      </div>
    </header>
  );
}
