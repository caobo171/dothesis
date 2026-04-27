'use client';

// Credit purchase cards. Visual structure ported from the survify product;
// payment plumbing intentionally simplified — DoThesis only uses Stripe today
// (Paddle/Polar/PayPal integrations from the source were not brought over).
//
// Per-card flow:
//   user picks quantity → click "Buy" → POST /api/credit/purchase with the
//   total credit amount → backend creates a Stripe Checkout Session and
//   returns its URL → we redirect.

import { FC, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'react-toastify';
import { DollarSign, Plus, Award, Ticket, Minus } from 'lucide-react';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code, PRICING_PACKAGES, CreditPackage } from '@/lib/core/Constants';
import { clsx } from 'clsx';

interface Props {
  // For modal use — smaller cards.
  compact?: boolean;
  onSuccess?: () => void;
}

const PricePackages: FC<Props> = ({ compact = false }) => {
  const router = useRouter();
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>(() =>
    Object.fromEntries(PRICING_PACKAGES.map((p) => [p.id, 1])),
  );

  const updateQuantity = (id: string, delta: number) => {
    setQuantities((prev) => ({
      ...prev,
      [id]: Math.max(1, Math.min(99, (prev[id] || 1) + delta)),
    }));
  };

  const handleBuy = async (pkg: CreditPackage) => {
    setProcessingId(pkg.id);
    try {
      const qty = quantities[pkg.id] || 1;
      const totalCredits = pkg.credit * qty;
      const res = await Fetch.postWithAccessToken<any>('/api/credit/purchase', {
        amount: totalCredits,
      });
      if (res.data.code === Code.Success && res.data.data?.url) {
        // Redirect to Stripe Checkout. Success/cancel URLs are configured server-side.
        window.location.href = res.data.data.url;
        return;
      }
      toast.error(res.data.message || 'Failed to start checkout');
    } catch (err: any) {
      toast.error('Checkout error');
    } finally {
      setProcessingId(null);
    }
  };

  const iconFor = (id: string) => {
    const cls = compact ? 'w-5 h-5' : 'w-6 h-6';
    if (id === 'starter') return <DollarSign className={`${cls} text-primary`} />;
    if (id === 'standard') return <Plus className={`${cls} text-primary`} />;
    if (id === 'expert') return <Award className={`${cls} text-primary`} />;
    return <Ticket className={`${cls} text-primary`} />;
  };

  return (
    <div
      className={clsx(
        'grid grid-cols-1 gap-4',
        compact ? 'md:grid-cols-3' : 'md:grid-cols-2 lg:grid-cols-3',
      )}
    >
      {PRICING_PACKAGES.map((pkg) => {
        const qty = quantities[pkg.id] || 1;
        const totalPrice = pkg.price * qty;
        const totalCredits = pkg.credit * qty;
        const isProcessing = processingId === pkg.id;

        return (
          <div
            key={pkg.id}
            className={clsx(
              'relative bg-white rounded-2xl border transition shadow-sm hover:shadow-md flex flex-col',
              pkg.highlight ? 'border-primary' : 'border-rule',
              compact ? 'p-4' : 'p-6',
            )}
          >
            {pkg.highlight && (
              <span className="absolute -top-2.5 left-4 px-2 py-0.5 bg-primary text-white text-[10px] font-semibold uppercase tracking-wider rounded-full">
                Popular
              </span>
            )}

            <div
              className={clsx(
                'rounded-xl bg-bg-blue flex items-center justify-center mb-3',
                compact ? 'w-10 h-10' : 'w-12 h-12',
              )}
            >
              {iconFor(pkg.id)}
            </div>

            <h3
              className={clsx(
                'font-semibold text-ink mb-1',
                compact ? 'text-base' : 'text-lg',
              )}
            >
              {pkg.name}
            </h3>
            {!compact && (
              <p className="text-sm text-ink-muted mb-4 flex-grow">{pkg.description}</p>
            )}

            <div className="flex items-baseline gap-2 mb-3">
              <span className={clsx('font-bold text-ink', compact ? 'text-2xl' : 'text-3xl')}>
                ${pkg.price}
              </span>
              {pkg.old_price > pkg.price && (
                <span className="text-sm text-ink-muted line-through">${pkg.old_price}</span>
              )}
              <span className="text-xs text-ink-muted">/ pack</span>
            </div>

            <div className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-full border border-primary/30 bg-bg-blue px-3 py-1 text-xs font-semibold text-primary">
              <Ticket className="w-3.5 h-3.5" />
              {pkg.credit.toLocaleString()} credits / pack
            </div>

            {/* Quantity stepper */}
            <div className="flex items-center justify-between mb-3 rounded-lg bg-bg-soft p-2">
              <span className="text-xs font-medium text-ink-muted">Quantity</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => updateQuantity(pkg.id, -1)}
                  disabled={qty <= 1}
                  aria-label="Decrease quantity"
                  className="w-7 h-7 flex items-center justify-center rounded-md border border-rule bg-white hover:bg-bg-soft disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Minus className="w-3.5 h-3.5 text-ink-soft" />
                </button>
                <span className="text-sm font-semibold text-ink w-7 text-center font-mono">
                  {qty}
                </span>
                <button
                  type="button"
                  onClick={() => updateQuantity(pkg.id, 1)}
                  disabled={qty >= 99}
                  aria-label="Increase quantity"
                  className="w-7 h-7 flex items-center justify-center rounded-md border border-rule bg-white hover:bg-bg-soft disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus className="w-3.5 h-3.5 text-ink-soft" />
                </button>
              </div>
            </div>

            {/* Total summary, only when qty > 1 */}
            {qty > 1 && (
              <div className="mb-3 rounded-lg bg-bg-blue px-3 py-2 flex items-center justify-between text-sm">
                <span className="text-ink-muted">Total</span>
                <div className="text-right">
                  <span className="font-bold text-primary">${totalPrice}</span>
                  <span className="text-xs text-primary/70 ml-2">
                    ({totalCredits.toLocaleString()} credits)
                  </span>
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={() => handleBuy(pkg)}
              disabled={isProcessing}
              className="w-full px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Starting checkout…' : qty > 1 ? `Buy for $${totalPrice}` : 'Buy now'}
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default PricePackages;
