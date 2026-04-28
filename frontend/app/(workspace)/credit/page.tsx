'use client';

// /credit — buy-credits page. Method-tab choice is auto-set based on the
// browser's timezone:
//   Vietnam timezone -> Sepay default (bank QR), with International tab available
//   anywhere else    -> International default (Polar/PayPal/Paddle), with Sepay tab available
//
// Both options are always reachable; the tabs just bias the default.

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { CheckCircle, AlertCircle, Ticket, Globe2, Banknote } from 'lucide-react';
import { clsx } from 'clsx';
import { useMe } from '@/hooks/user';
import { useBalance } from '@/hooks/credit';
import { isVietnameseTimezone } from '@/lib/util/timezone';
import PricePackages from '@/components/credit/PricePackages';
import SepayPay from '@/components/credit/SepayPay';

type Method = 'international' | 'sepay';

export default function CreditPage() {
  const { data: user } = useMe();
  const { balance } = useBalance();
  const params = useSearchParams();
  const status = params?.get('purchase');

  // Default method based on timezone. Stable across renders so the tab
  // doesn't flicker once the page mounts.
  const [method, setMethod] = useState<Method | null>(null);
  useEffect(() => {
    setMethod(isVietnameseTimezone() ? 'sepay' : 'international');
  }, []);

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
      <p className="text-sm text-ink-muted mb-5">
        Credits power humanize, plagiarism, and citation runs.
      </p>

      {/* Method tabs */}
      {method && (
        <div className="inline-flex items-center bg-bg-soft rounded-xl p-1 mb-5 text-sm">
          <button
            type="button"
            onClick={() => setMethod('international')}
            className={clsx(
              'flex items-center gap-2 px-4 py-1.5 rounded-lg transition',
              method === 'international'
                ? 'bg-white text-ink shadow-sm font-medium'
                : 'text-ink-muted hover:text-ink-soft',
            )}
          >
            <Globe2 className="w-4 h-4" />
            International (USD)
          </button>
          <button
            type="button"
            onClick={() => setMethod('sepay')}
            className={clsx(
              'flex items-center gap-2 px-4 py-1.5 rounded-lg transition',
              method === 'sepay'
                ? 'bg-white text-ink shadow-sm font-medium'
                : 'text-ink-muted hover:text-ink-soft',
            )}
          >
            <Banknote className="w-4 h-4" />
            Bank transfer (VND)
          </button>
        </div>
      )}

      {method === 'sepay' ? <SepayPay /> : <PricePackages />}

      <div className="mt-8 rounded-xl bg-bg-soft p-4 text-sm text-ink-soft">
        <h3 className="font-semibold text-ink mb-2">Notes</h3>
        <ul className="space-y-1 text-xs">
          <li>• Credits are non-refundable except where the tool fails to produce output.</li>
          <li>• International payments are processed by Polar / PayPal / Paddle.</li>
          <li>• Vietnamese bank transfers via Sepay arrive within 1–3 minutes after the bank settles.</li>
        </ul>
      </div>
    </section>
  );
}
