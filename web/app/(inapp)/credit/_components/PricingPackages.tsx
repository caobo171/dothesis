"use client";

import { Award, Landmark, Ticket, Wallet, X } from "lucide-react";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { apiFetch, swrFetcher } from "@/app/lib/api";
import type { CreditPackage } from "@/app/lib/credit-packages";

const PACKAGE_ICONS: Record<string, typeof Award> = {
  starter_package: Ticket,
  standard_package: Award,
  expert_package: Award,
};

/** SePay is a Vietnam-only bank transfer — only offer it to UTC+7 users. */
function isUtcPlus7(): boolean {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz === "Asia/Ho_Chi_Minh" || tz === "Asia/Saigon") return true;
  } catch {
    /* fall through to offset check */
  }
  return -new Date().getTimezoneOffset() / 60 === 7;
}

type Methods = { methods: string[]; sepay_enabled: boolean };
type SepayIntent = {
  order_id: string;
  memo: string;
  amount_vnd: number;
  qr_url: string;
  bank_code: string;
  account_number: string;
};

export function PricingPackages({ onSuccess }: { onSuccess?: () => void }) {
  const { data: packages, error } = useSWR<CreditPackage[]>("/credit/packages", swrFetcher);
  const { data: methods } = useSWR<Methods>("/credit/methods", swrFetcher);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sepay, setSepay] = useState<SepayIntent | null>(null);

  if (error) return <div className="text-red-700">Could not load packages.</div>;
  if (!packages) return <div className="text-ink-500">Loading…</div>;

  const available = methods?.methods ?? ["polar"];
  const showPayPal = available.includes("paypal");
  const showSepay = available.includes("sepay") && isUtcPlus7();

  async function polarBuy(pkg: CreditPackage) {
    setBusy(`polar:${pkg.id}`);
    setErr(null);
    try {
      const res = await apiFetch("/credit/checkout", {
        method: "POST",
        body: { package_id: pkg.id },
      });
      if (res?.checkout_url) {
        onSuccess?.();
        window.location.href = res.checkout_url;
        return;
      }
      setErr("Checkout could not be started (Polar may not be configured).");
    } catch (e: any) {
      setErr(e?.message || "Checkout failed.");
    } finally {
      setBusy(null);
    }
  }

  async function paypalBuy(pkg: CreditPackage) {
    setBusy(`paypal:${pkg.id}`);
    setErr(null);
    try {
      const res = await apiFetch("/credit/paypal/create-order", {
        method: "POST",
        body: { package_id: pkg.id },
      });
      if (res?.approval_url) {
        onSuccess?.();
        window.location.href = res.approval_url;
        return;
      }
      setErr("PayPal checkout could not be started.");
    } catch (e: any) {
      setErr(e?.message || "PayPal checkout failed.");
    } finally {
      setBusy(null);
    }
  }

  async function sepayBuy(pkg: CreditPackage) {
    setBusy(`sepay:${pkg.id}`);
    setErr(null);
    try {
      const res: SepayIntent = await apiFetch("/credit/sepay/intent", {
        method: "POST",
        body: { package_id: pkg.id },
      });
      setSepay(res);
    } catch (e: any) {
      setErr(e?.message || "Could not start SePay transfer.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {err && (
        <div className="sm:col-span-2 lg:col-span-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {err}
        </div>
      )}
      {packages.map((pkg) => {
        const Icon = PACKAGE_ICONS[pkg.id] || Award;
        return (
          <div
            key={pkg.id}
            className="flex flex-col rounded-2xl border border-ink-100 bg-white p-5 shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-ink-900">{pkg.name}</h3>
                <p className="text-xs text-ink-500">{pkg.credits.toLocaleString()} credits</p>
              </div>
            </div>

            <div className="mt-5 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-ink-900">${(pkg.price_cents / 100).toFixed(2)}</span>
              <span className="text-sm text-ink-400 line-through">${(pkg.old_price_cents / 100).toFixed(0)}</span>
            </div>

            <div className="mt-5 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => polarBuy(pkg)}
                disabled={busy !== null}
                className="rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
              >
                {busy === `polar:${pkg.id}` ? "Starting…" : "Pay by card"}
              </button>
              {showPayPal && (
                <button
                  type="button"
                  onClick={() => paypalBuy(pkg)}
                  disabled={busy !== null}
                  className="flex items-center justify-center gap-2 rounded-xl border border-ink-200 px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50"
                >
                  <Wallet className="h-4 w-4" />
                  {busy === `paypal:${pkg.id}` ? "Starting…" : "PayPal"}
                </button>
              )}
              {showSepay && (
                <button
                  type="button"
                  onClick={() => sepayBuy(pkg)}
                  disabled={busy !== null}
                  className="flex items-center justify-center gap-2 rounded-xl border border-ink-200 px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50"
                >
                  <Landmark className="h-4 w-4" />
                  {busy === `sepay:${pkg.id}` ? "Đang tạo…" : "Chuyển khoản (SePay)"}
                </button>
              )}
            </div>
          </div>
        );
      })}

      {sepay && (
        <SepayModal
          intent={sepay}
          onClose={() => setSepay(null)}
          onPaid={() => {
            setSepay(null);
            onSuccess?.();
          }}
        />
      )}
    </div>
  );
}

function SepayModal({
  intent,
  onClose,
  onPaid,
}: {
  intent: SepayIntent;
  onClose: () => void;
  onPaid: () => void;
}) {
  const [paid, setPaid] = useState(false);

  // Poll the order status until SePay's webhook flips it to "paid".
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const res = await apiFetch("/credit/order/status", {
          method: "POST",
          body: { order_id: intent.order_id },
        });
        if (res?.status === "paid" && !stop) {
          setPaid(true);
          setTimeout(onPaid, 1500);
          return;
        }
      } catch {
        /* keep polling */
      }
      if (!stop) setTimeout(tick, 4000);
    };
    const id = setTimeout(tick, 4000);
    return () => {
      stop = true;
      clearTimeout(id);
    };
  }, [intent.order_id, onPaid]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 text-ink-400 hover:text-ink-700"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
        <h3 className="text-base font-semibold text-ink-900">Chuyển khoản qua SePay</h3>
        <p className="mt-1 text-xs text-ink-500">
          Quét mã QR hoặc chuyển khoản đúng nội dung. Tín dụng được cộng tự động sau 1–2 phút.
        </p>

        {paid ? (
          <div className="mt-6 rounded-xl bg-green-50 px-4 py-6 text-center text-green-700">
            Đã nhận thanh toán! Tín dụng đã được cộng.
          </div>
        ) : (
          <>
            <div className="mt-4 flex justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={intent.qr_url} alt="SePay QR" className="h-56 w-56 rounded-lg border border-ink-100" />
            </div>
            <dl className="mt-4 space-y-1 text-sm">
              <Row label="Ngân hàng" value={intent.bank_code} />
              <Row label="Số tài khoản" value={intent.account_number} />
              <Row label="Số tiền" value={`${intent.amount_vnd.toLocaleString("vi-VN")} ₫`} />
              <Row label="Nội dung" value={intent.memo} mono />
            </dl>
            <p className="mt-3 text-center text-xs text-ink-400">Đang chờ thanh toán…</p>
          </>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-500">{label}</dt>
      <dd className={`font-medium text-ink-900 ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}
