'use client';

import { useBalance } from '@/hooks/credit';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

export function CreditPill() {
  const { balance } = useBalance();
  const [showBuy, setShowBuy] = useState(false);

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
    <div className="relative">
      <button
        onClick={() => setShowBuy(!showBuy)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-blue rounded-full hover:bg-primary/10 transition"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0022FF" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v12M8 10h8M8 14h8" />
        </svg>
        <span className="text-xs font-semibold text-primary font-mono">{balance}</span>
      </button>

      {showBuy && (
        <div className="absolute right-0 top-full mt-2 bg-white rounded-xl border border-rule shadow-lg p-4 w-48 z-50">
          <p className="text-xs font-semibold text-ink mb-2">Buy credits</p>
          <div className="space-y-1.5">
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
  );
}
