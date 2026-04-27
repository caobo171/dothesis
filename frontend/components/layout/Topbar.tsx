'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ChevronRight, MessageSquare, HelpCircle, Zap } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'react-toastify';
import { useBalance } from '@/hooks/credit';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

const TITLES: Record<string, string> = {
  '/humanizer': 'Humanizer',
  '/auto-cite': 'Auto-Cite',
  '/library': 'Library',
  '/history': 'History',
};

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { balance } = useBalance();
  const [showBuy, setShowBuy] = useState(false);

  // Top-level breadcrumb derived from the current path. The first segment maps
  // to a friendly label via TITLES; deeper segments fall back to the raw slug.
  // Anything outside the workspace map is shown as 'Workspace > <segment>'.
  const segments = pathname.split('/').filter(Boolean);
  const lastSegment = segments[segments.length - 1] || '';
  const title = TITLES[`/${segments[0] || ''}`] || lastSegment.replace(/-/g, ' ');

  const handleBuy = async (amount: number) => {
    const res = await Fetch.postWithAccessToken<any>('/api/credit/purchase', { amount });
    if (res.data.code === Code.Success && res.data.data.url) {
      window.location.href = res.data.data.url;
    } else {
      toast.error(res.data.message || 'Failed to create checkout');
    }
    setShowBuy(false);
  };

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

        {/* Credits pill — clicking opens the buy popover */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowBuy((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-blue text-primary hover:bg-primary/10 transition"
          >
            <Zap className="w-4 h-4 fill-current" />
            <span className="text-sm font-semibold font-mono">{balance.toLocaleString()}</span>
            <span className="text-sm">credits</span>
          </button>

          {showBuy && (
            <div className="absolute right-0 top-full mt-2 bg-white rounded-xl border border-rule shadow-lg p-4 w-56 z-50">
              <p className="text-xs font-semibold text-ink mb-2">Buy credits</p>
              <div className="space-y-1">
                {[
                  { credits: 50, price: '$5' },
                  { credits: 100, price: '$10' },
                  { credits: 500, price: '$50' },
                ].map((pkg) => (
                  <button
                    key={pkg.credits}
                    onClick={() => handleBuy(pkg.credits)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-bg-soft transition text-sm"
                  >
                    <span className="font-mono font-medium text-ink">{pkg.credits}</span>
                    <span className="text-ink-muted">{pkg.price}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
