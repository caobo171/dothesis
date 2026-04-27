'use client';

// /credit — dedicated buy-credits page. The topbar credit pill and the sidebar
// "Buy credits" CTA both route here. Card layout ported visually from survify;
// payment runs through the existing Stripe /api/credit/purchase route.

import { useSearchParams } from 'next/navigation';
import { CheckCircle, AlertCircle, Ticket } from 'lucide-react';
import { useMe } from '@/hooks/user';
import { useBalance } from '@/hooks/credit';
import PricePackages from '@/components/credit/PricePackages';

export default function CreditPage() {
  const { data: user } = useMe();
  const { balance } = useBalance();
  const params = useSearchParams();
  // Stripe redirect appends ?purchase=success or ?purchase=cancel back to /humanizer,
  // but if we route checkout returns here we can show a status banner. Future-friendly.
  const status = params?.get('purchase');

  return (
    <section className="max-w-5xl mx-auto">
      {status === 'success' && (
        <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success/5 p-4 mb-4">
          <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
          <p className="text-sm text-success">Payment successful. Your credits will appear shortly.</p>
        </div>
      )}
      {status === 'cancel' && (
        <div className="flex items-center gap-3 rounded-xl border border-warn/30 bg-warn/5 p-4 mb-4">
          <AlertCircle className="w-5 h-5 text-warn flex-shrink-0" />
          <p className="text-sm text-warn">Checkout cancelled. No charges were made.</p>
        </div>
      )}

      {/* Header row: user + balance */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 pb-4 border-b border-rule">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-white text-sm font-semibold">
            {user?.username?.charAt(0)?.toUpperCase() || 'U'}
          </div>
          <div>
            <div className="text-sm font-semibold text-ink">{user?.username || 'You'}</div>
            <div className="text-xs text-ink-muted">{user?.email || ''}</div>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-full bg-bg-blue px-3 py-1.5">
          <Ticket className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold text-primary font-mono">
            {balance.toLocaleString()}
          </span>
          <span className="text-sm text-primary">credits</span>
        </div>
      </div>

      <h1 className="font-serif text-3xl text-ink mb-1">Buy credits</h1>
      <p className="text-sm text-ink-muted mb-6">
        Credits power humanize, plagiarism, and citation runs. Pick a pack — bigger packs
        carry more credits per dollar.
      </p>

      <PricePackages />

      <div className="mt-8 rounded-xl bg-bg-soft p-4 text-sm text-ink-soft">
        <h3 className="font-semibold text-ink mb-2">Notes</h3>
        <ul className="space-y-1 text-xs">
          <li>• Credits are non-refundable except where the tool fails to produce output.</li>
          <li>• Purchases are processed by Stripe; you'll be redirected to a hosted checkout.</li>
          <li>• Credits arrive within a minute of payment confirmation. Refresh if delayed.</li>
        </ul>
      </div>
    </section>
  );
}
