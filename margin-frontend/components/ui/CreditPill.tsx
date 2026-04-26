'use client';

import { useBalance } from '@/hooks/credit';

export function CreditPill() {
  const { balance } = useBalance();

  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-blue rounded-full">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0022FF" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v12M8 10h8M8 14h8" />
      </svg>
      <span className="text-xs font-semibold text-primary font-mono">{balance}</span>
    </div>
  );
}
