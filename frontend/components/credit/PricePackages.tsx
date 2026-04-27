'use client';

// Three-provider credit checkout, ported from survify's PricingPackages.
// Each card supports a primary provider button (driven by PAYMENT_PROVIDER
// in Constants) plus a "Pay with PayPal" fallback when the primary is Polar.
//
// Stripped from the survify original:
//   - PostHog event tracking (DoThesis doesn't run PostHog).
//   - The credit_id (`idcredit`) field — DoThesis uses user._id directly.
//   - Refund-policy block — moved into the page-level Notes section.

import { FC, useEffect, useState } from 'react';
import { DollarSign, Plus, Award, Ticket, Minus } from 'lucide-react';
import { toast } from 'react-toastify';
import { clsx } from 'clsx';
import { useMe } from '@/hooks/user';
import Fetch from '@/lib/core/fetch/Fetch';
import {
  Code,
  PRICING_PACKAGES,
  PADDLE_CLIENT_TOKEN,
  PAYMENT_PROVIDER,
  IS_SANDBOX,
  PaymentProvider,
  CreditPackage,
} from '@/lib/core/Constants';

declare global {
  interface Window {
    Paddle?: any;
  }
}

interface Props {
  // For modal use — smaller cards.
  compact?: boolean;
  onSuccess?: () => void;
}

const PricePackages: FC<Props> = ({ compact = false, onSuccess }) => {
  const { data: me } = useMe();
  // Polar / PayPal don't need a client-side SDK. Paddle does — we lazy-load
  // its script tag and flip providerLoaded once it's initialised.
  const [providerLoaded, setProviderLoaded] = useState(
    PAYMENT_PROVIDER === 'paypal' || PAYMENT_PROVIDER === 'polar',
  );
  const [processingPackage, setProcessingPackage] = useState<string | null>(null);
  const [activeProvider, setActiveProvider] = useState<PaymentProvider>(PAYMENT_PROVIDER);
  const [quantities, setQuantities] = useState<Record<string, number>>(() =>
    Object.fromEntries(PRICING_PACKAGES.map((p) => [p.id, 1])),
  );

  const updateQuantity = (id: string, delta: number) => {
    setQuantities((prev) => ({
      ...prev,
      [id]: Math.max(1, Math.min(99, (prev[id] || 1) + delta)),
    }));
  };

  // Paddle bootstrap. Same pattern as survify: load paddle.js if our primary
  // provider is paddle and we have an authenticated user. Skipped otherwise.
  useEffect(() => {
    if (!me) return;
    if (PAYMENT_PROVIDER !== 'paddle') return;
    if (window.Paddle) {
      setProviderLoaded(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.paddle.com/paddle/v2/paddle.js';
    script.async = true;
    script.onload = () => {
      if (window.Paddle) {
        if (IS_SANDBOX) {
          window.Paddle.Environment.set('sandbox');
        }
        window.Paddle.Initialize({
          token: PADDLE_CLIENT_TOKEN,
          pwCustomer: 'ctm_' + me?.id,
        });
        setProviderLoaded(true);
      }
    };
    document.body.appendChild(script);
  }, [me]);

  // Polar status check. If POLAR_ACCESS_TOKEN/POLAR_PRODUCT_ID aren't set
  // server-side, fall back to PayPal so the buttons still do something.
  useEffect(() => {
    if (PAYMENT_PROVIDER !== 'polar') return;
    Fetch.postWithAccessToken<any>('/api/order/polar/status', {})
      .then((res: any) => {
        const enabled = res?.data?.data?.enabled;
        if (!enabled) setActiveProvider('paypal');
      })
      .catch(() => setActiveProvider('paypal'));
  }, []);

  const handlePaddleCheckout = (pkg: CreditPackage) => {
    if (!window.Paddle) {
      toast.error('Paddle is not loaded yet');
      return;
    }
    const qty = quantities[pkg.id] || 1;
    window.Paddle.Checkout.open({
      items: [{ priceId: pkg.paddle_price_id, quantity: qty }],
      customData: {
        user_id: me?.id,
        packageId: pkg.id,
        credits: pkg.credit * qty,
        quantity: qty,
      },
      settings: { successUrl: window.location.href },
      eventCallback: (event: any) => {
        if (event.name === 'checkout.completed') {
          window.Paddle.Checkout.close();
          onSuccess?.();
          window.location.reload();
        }
      },
    });
  };

  const handlePolarCheckout = async (pkg: CreditPackage) => {
    setProcessingPackage(pkg.id);
    try {
      const qty = quantities[pkg.id] || 1;
      const response = await Fetch.postWithAccessToken<any>('/api/order/polar/create-checkout', {
        packageId: pkg.id,
        quantity: qty,
      });
      const data = response.data as any;
      if (data.code !== Code.Success || !data.data?.checkoutUrl) {
        toast.error(data.message || 'Failed to start Polar checkout');
        setProcessingPackage(null);
        return;
      }
      window.location.href = data.data.checkoutUrl;
    } catch (err) {
      toast.error('Polar checkout failed');
      setProcessingPackage(null);
    }
  };

  const handlePayPalCheckout = async (pkg: CreditPackage) => {
    setProcessingPackage(pkg.id);
    try {
      const qty = quantities[pkg.id] || 1;
      const createResponse = await Fetch.postWithAccessToken<any>('/api/order/paypal/create-order', {
        packageId: pkg.id,
        price: pkg.price * qty,
        credits: pkg.credit * qty,
        quantity: qty,
      });
      const createData = createResponse.data as any;
      if (createData.code !== Code.Success || !createData.data?.id) {
        toast.error(createData.message || 'Failed to start PayPal checkout');
        setProcessingPackage(null);
        return;
      }
      // Redirect to PayPal's approval URL.
      const approvalUrl = createData.data.links?.find(
        (link: any) => link.rel === 'payer-action' || link.rel === 'approve',
      )?.href;
      if (approvalUrl) {
        window.location.href = approvalUrl;
      } else {
        toast.error('No approval URL on PayPal response');
        setProcessingPackage(null);
      }
    } catch {
      toast.error('PayPal checkout failed');
      setProcessingPackage(null);
    }
  };

  const handlePrimaryClick = (pkg: CreditPackage) => {
    if (!providerLoaded) {
      toast.error('Payment provider is not loaded yet');
      return;
    }
    if (!me?.id) {
      toast.error('You need to be signed in');
      return;
    }
    if (activeProvider === 'polar') return handlePolarCheckout(pkg);
    if (activeProvider === 'paddle') return handlePaddleCheckout(pkg);
    return handlePayPalCheckout(pkg);
  };

  const iconFor = (id: string) => {
    const cls = compact ? 'w-5 h-5' : 'w-6 h-6';
    if (id === 'starter_package') return <DollarSign className={`${cls} text-primary`} />;
    if (id === 'standard_package') return <Plus className={`${cls} text-primary`} />;
    if (id === 'expert_package') return <Award className={`${cls} text-primary`} />;
    return <Ticket className={`${cls} text-primary`} />;
  };

  const descriptionFor = (id: string) => {
    if (id === 'starter_package') return 'Try the product with basic features.';
    if (id === 'standard_package') return 'Standard quality and quantity for regular use.';
    if (id === 'expert_package') return 'Best price per credit. Share with classmates.';
    return '';
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
        const isProcessing = processingPackage === pkg.id;

        return (
          <div
            key={pkg.id}
            className={clsx(
              'bg-white rounded-2xl border border-rule shadow-sm hover:shadow-md transition flex flex-col',
              compact ? 'p-4' : 'p-6',
            )}
          >
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
                'font-semibold text-ink mb-1 capitalize',
                compact ? 'text-base' : 'text-lg',
              )}
            >
              {pkg.name}
            </h3>
            {!compact && (
              <p className="text-sm text-ink-muted mb-4 flex-grow">{descriptionFor(pkg.id)}</p>
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
              onClick={() => handlePrimaryClick(pkg)}
              disabled={!providerLoaded || isProcessing}
              className="w-full bg-primary hover:bg-primary-dark disabled:opacity-60 text-white font-semibold py-2.5 rounded-xl transition"
            >
              {isProcessing ? 'Processing…' : qty > 1 ? `Pay $${totalPrice}` : 'Buy now'}
            </button>

            {/* Polar primary → offer PayPal as a one-click fallback. */}
            {activeProvider === 'polar' && (
              <button
                onClick={() => handlePayPalCheckout(pkg)}
                disabled={isProcessing}
                className="w-full text-ink-muted hover:text-ink-soft font-medium py-1.5 text-xs mt-1 transition"
              >
                Or pay with PayPal
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default PricePackages;
