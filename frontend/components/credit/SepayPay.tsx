'use client';

// Sepay (Vietnamese bank transfer) credit purchase. Shown to users in a
// Vietnamese timezone. Calls /api/me/bank.info to get a per-package QR + memo,
// then renders a card with the QR image and copy-able transfer details.
//
// User flow:
//   1. Pick a package.
//   2. Scan the QR with their banking app, OR copy bank account + memo
//      and transfer manually.
//   3. Wait — Sepay's webhook fires once the bank settles the transfer
//      (usually 1–3 minutes), and credits land via the same path Polar/PayPal
//      use. The page polls /api/credit/balance every 10s while open so the
//      user sees their balance update without a refresh.

import { FC, useEffect, useState } from 'react';
import useSWR from 'swr';
import { Copy, RefreshCw, Ticket } from 'lucide-react';
import { toast } from 'react-toastify';
import { clsx } from 'clsx';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';
import { useBalance } from '@/hooks/credit';

type SepayPackage = {
  id: string;
  credit: number;
  price_vnd: number;
  memo: string;
  qr_url: string;
};

type BankInfo = {
  bank: { name: string; number: string; provider: string };
  idcredit: number;
  memo_prefix: string;
  packages: SepayPackage[];
};

const fetcher = async (key: [string, Record<string, any>]) => {
  const [url, params] = key;
  const res = await Fetch.postWithAccessToken<any>(url, params);
  return res.data;
};

const formatVnd = (n: number) => `${n.toLocaleString('vi-VN')}₫`;

const PRESETS = [
  { id: 'starter_package', label: 'Starter' },
  { id: 'standard_package', label: 'Standard' },
  { id: 'expert_package', label: 'Expert' },
];

const SepayPay: FC = () => {
  const { data, isLoading } = useSWR<{ code: number; data: BankInfo; message?: string }>(
    ['/api/me/bank.info', {}],
    fetcher,
  );
  const { mutate: refreshBalance } = useBalance();

  const info = data?.code === Code.Success ? data.data : undefined;
  const [selectedId, setSelectedId] = useState<string>('standard_package');

  // Once selected/info loaded, find the matching package definition.
  const selected = info?.packages.find((p) => p.id === selectedId) || info?.packages[0];

  // Auto-poll the balance while this card is mounted so a successful Sepay
  // webhook reflects without the user reloading. Cleared on unmount.
  useEffect(() => {
    if (!info) return;
    const id = setInterval(() => refreshBalance(), 10_000);
    return () => clearInterval(id);
  }, [info, refreshBalance]);

  const copy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch {
      toast.error('Copy failed');
    }
  };

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-rule bg-white p-6 text-center text-sm text-ink-muted">
        Đang tải thông tin chuyển khoản…
      </div>
    );
  }
  if (!info || !selected) {
    return (
      <div className="rounded-2xl border border-rule bg-white p-6 text-center text-sm text-ink-muted">
        {data?.message || 'Không lấy được thông tin Sepay'}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Pack picker */}
      <div className="grid grid-cols-3 gap-2">
        {PRESETS.map((p) => {
          const pkg = info.packages.find((x) => x.id === p.id);
          if (!pkg) return null;
          const active = selected.id === pkg.id;
          return (
            <button
              key={pkg.id}
              type="button"
              onClick={() => setSelectedId(pkg.id)}
              className={clsx(
                'rounded-xl border p-3 text-left transition',
                active
                  ? 'border-primary bg-bg-blue ring-2 ring-primary/20'
                  : 'border-rule bg-white hover:bg-bg-soft',
              )}
            >
              <div className="text-xs uppercase tracking-wider text-ink-muted">{p.label}</div>
              <div className={clsx('text-base font-semibold mt-0.5', active ? 'text-primary' : 'text-ink')}>
                {formatVnd(pkg.price_vnd)}
              </div>
              <div className="text-xs text-ink-muted">{pkg.credit.toLocaleString()} credits</div>
            </button>
          );
        })}
      </div>

      {/* QR + bank info card */}
      <div className="rounded-2xl border border-rule bg-white p-5 grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* QR */}
        <div className="flex flex-col items-center justify-center">
          <img
            src={selected.qr_url}
            alt={`Sepay QR — ${selected.id}`}
            className="w-56 h-56 rounded-xl border border-rule"
          />
          <p className="mt-2 text-xs text-ink-muted text-center">
            Quét bằng app ngân hàng để chuyển khoản chính xác số tiền và nội dung.
          </p>
        </div>

        {/* Manual transfer details */}
        <div className="space-y-3 text-sm">
          <Row k="Ngân hàng" v={info.bank.name} />
          <Row k="Số tài khoản" v={info.bank.number} onCopy={() => copy(info.bank.number, 'Số tài khoản')} />
          <Row
            k="Số tiền"
            v={
              <span className="font-semibold text-primary">
                {formatVnd(selected.price_vnd)}
              </span>
            }
            onCopy={() => copy(String(selected.price_vnd), 'Số tiền')}
          />
          <Row
            k="Nội dung"
            v={<span className="font-mono">{selected.memo}</span>}
            onCopy={() => copy(selected.memo, 'Nội dung')}
          />
          <Row
            k="Bạn sẽ nhận"
            v={
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-bg-blue px-2 py-0.5 text-xs font-semibold text-primary">
                <Ticket className="w-3 h-3" /> {selected.credit.toLocaleString()} credits
              </span>
            }
          />
          <div className="rounded-lg bg-bg-soft p-3 text-xs text-ink-soft flex items-start gap-2">
            <RefreshCw className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Sau khi chuyển khoản, credits sẽ được cộng tự động trong vòng 1–3 phút.
              Trang này tự động cập nhật.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

function Row({
  k,
  v,
  onCopy,
}: {
  k: string;
  v: React.ReactNode;
  onCopy?: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-rule pb-2 last:border-b-0 last:pb-0">
      <dt className="text-xs uppercase tracking-wider text-ink-muted">{k}</dt>
      <dd className="flex items-center gap-2 text-ink">
        {v}
        {onCopy && (
          <button
            type="button"
            onClick={onCopy}
            aria-label="Copy"
            className="text-ink-muted hover:text-primary transition"
          >
            <Copy className="w-3.5 h-3.5" />
          </button>
        )}
      </dd>
    </div>
  );
}

export default SepayPay;
