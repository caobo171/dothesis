'use client';

// /credit/paypal-return — landing page after the user approves on PayPal.
// PayPal redirects here with `token=<orderId>` (and PayerID, but we don't
// need it for capture). We POST to /order/paypal/capture-order which both
// captures the funds and grants credits server-side.
//
// On success → redirect to /credit?purchase=success.
// On failure → redirect back with an error toast.

import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';
import { Loader2 } from 'lucide-react';

export default function PayPalReturnPage() {
  const params = useSearchParams();
  const router = useRouter();
  // Guard against React 18 strict-mode double-effect firing capture twice.
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const orderId = params?.get('token');
    if (!orderId) {
      toast.error('Missing PayPal order id');
      router.replace('/credit');
      return;
    }

    (async () => {
      try {
        const res = await Fetch.postWithAccessToken<any>('/api/order/paypal/capture-order', { orderId });
        const data = res.data as any;
        if (data.code === Code.Success) {
          router.replace('/credit?purchase=success');
        } else {
          toast.error(data.message || 'Capture failed');
          router.replace('/credit?purchase=cancel');
        }
      } catch {
        toast.error('Capture failed');
        router.replace('/credit?purchase=cancel');
      }
    })();
  }, [params, router]);

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Loader2 className="w-6 h-6 text-primary animate-spin mb-3" />
      <p className="text-sm text-ink-soft">Confirming your payment with PayPal…</p>
      <p className="text-xs text-ink-muted mt-1">Don't close this tab.</p>
    </div>
  );
}
