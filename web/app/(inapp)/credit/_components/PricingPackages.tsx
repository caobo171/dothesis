"use client";

import { Award, Gem, Landmark, Star, Wallet, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { apiFetch, swrFetcher } from "@/app/lib/api";
import type { CreditPackage } from "@/app/lib/credit-packages";
import type { MessageKey } from "@/app/lib/i18n/messages/en";
import { useLocale, useTn } from "@/app/lib/i18n/LocaleProvider";

const PACKAGE_ICONS: Record<string, typeof Award> = {
  starter_package: Zap,
  standard_package: Star,
  expert_package: Gem,
};

const PKG_NAME: Record<string, MessageKey> = {
  starter_package: "credit.pkg.starter_package",
  standard_package: "credit.pkg.standard_package",
  expert_package: "credit.pkg.expert_package",
};

const PKG_BLURB: Record<string, MessageKey> = {
  starter_package: "credit.blurb.starter_package",
  standard_package: "credit.blurb.standard_package",
  expert_package: "credit.blurb.expert_package",
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

/** Dong, VN-style: dot thousands separators and a trailing ₫ ("657.237 ₫"). */
function formatVnd(amount: number): string {
  return `${amount.toLocaleString("vi-VN")} ₫`;
}

function savePct(pkg: CreditPackage): number {
  if (!pkg.old_price_cents) return 0;
  return Math.round((1 - pkg.price_cents / pkg.old_price_cents) * 100);
}

function perThousand(pkg: CreditPackage, vnd: boolean): string {
  if (!pkg.credits) return "";
  if (vnd) return formatVnd(Math.round((pkg.price_vnd / pkg.credits) * 1000));
  const usd = (pkg.price_cents / 100 / pkg.credits) * 1000;
  return `$${usd.toFixed(2)}`;
}

function formatRuns(n: number, numberLocale: string): string {
  if (Number.isInteger(n)) return String(n);
  return n.toLocaleString(numberLocale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function cheaperThanStarter(pkg: CreditPackage, starter: CreditPackage | undefined): number {
  if (!starter || !starter.credits || !pkg.credits) return 0;
  const a = pkg.price_cents / pkg.credits;
  const b = starter.price_cents / starter.credits;
  if (b <= 0 || a >= b) return 0;
  return Math.round((1 - a / b) * 100);
}

type Methods = { methods: string[]; sepay_enabled: boolean };
type SepayIntent = {
  order_id: string;
  /** Bare payment code (DTS1234) — what the webhook matches on. */
  memo: string;
  /** What the payer must type: the code, plus the bank's routing prefix if any. */
  transfer_content: string;
  amount_vnd: number;
  qr_url: string;
  bank_code: string;
  bank_name: string;
  account_number: string;
};

export function PricingPackages({ onSuccess }: { onSuccess?: () => void }) {
  const { t, locale } = useLocale();
  const tn = useTn();
  const numberLocale = locale === "vi" ? "vi-VN" : "en-US";
  const { data: packages, error } = useSWR<CreditPackage[]>("/credit/packages", swrFetcher);
  const { data: methods } = useSWR<Methods>("/credit/methods", swrFetcher);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sepay, setSepay] = useState<SepayIntent | null>(null);

  if (error) return <div className="text-red-700">{t("credit.loadError")}</div>;
  if (!packages) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-72 rounded-2xl bg-ink-100 animate-pulse" />
        ))}
      </div>
    );
  }

  const available = methods?.methods ?? ["polar"];
  const showPayPal = available.includes("paypal");
  const showSepay = available.includes("sepay") && isUtcPlus7();
  const starter = packages.find((p) => p.id === "starter_package");

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
    <div>
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5 items-stretch">
      {err && (
        <div className="sm:col-span-2 lg:col-span-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {err}
        </div>
      )}
      {packages.map((pkg) => {
        const Icon = PACKAGE_ICONS[pkg.id] || Award;
        // Decision: Standard is the featured tier, not Expert. Stay on the
        // light page (ring + wash, not a black invert) so it doesn't look
        // pasted in. Expert already wins on unit price via the rate chip.
        const featured = pkg.id === "standard_package";
        const bestRate = pkg.id === "expert_package";
        const pct = savePct(pkg);
        const vsStarter = cheaperThanStarter(pkg, starter);
        const price = showSepay
          ? formatVnd(pkg.price_vnd)
          : `$${(pkg.price_cents / 100).toFixed(2)}`;
        const oldPrice = showSepay
          ? formatVnd(pkg.old_price_vnd)
          : `$${(pkg.old_price_cents / 100).toFixed(0)}`;
        const nameKey = PKG_NAME[pkg.id];
        const blurbKey = PKG_BLURB[pkg.id];

        return (
          <div
            key={pkg.id}
            className={
              featured
                ? "relative flex flex-col rounded-2xl border border-primary-200 bg-primary-50/70 p-6 shadow-[0_12px_32px_-16px_rgba(28,46,255,0.35)] ring-2 ring-primary-600 lg:-mt-1"
                : "relative flex flex-col rounded-2xl border border-ink-200 bg-white p-6 shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md"
            }
          >
            {(featured || bestRate || pct > 0) && (
              <div className="mb-4 flex flex-wrap items-center gap-1.5">
                {featured && (
                  <span className="rounded-full bg-primary-600 px-2.5 py-0.5 text-[11px] font-semibold text-white">
                    {t("credit.featured")}
                  </span>
                )}
                {bestRate && (
                  <span className="rounded-full bg-primary-600 px-2.5 py-0.5 text-[11px] font-semibold text-white">
                    {t("credit.bestRate")}
                  </span>
                )}
                {pct > 0 && (
                  <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] font-semibold text-primary-700 ring-1 ring-primary-100">
                    {t("credit.save", { pct })}
                  </span>
                )}
              </div>
            )}

            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-primary-600 ring-1 ring-primary-100">
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-ink-900">
                  {nameKey ? t(nameKey) : pkg.name}
                </h3>
                <p className="text-sm text-ink-500">
                  {blurbKey ? t(blurbKey) : t("credit.credits", { count: pkg.credits.toLocaleString(numberLocale) })}
                </p>
              </div>
            </div>

            {/* VN users pay by bank transfer in dong, so quote dong — seeing
                $24.99 on the card and being asked for ₫657.237 in the QR reads
                like a bait-and-switch. Everyone else still sees USD. */}
            <div className="mt-6 flex items-baseline gap-2">
              <span className="text-4xl font-extrabold tabular-nums tracking-tight text-ink-900">
                {price}
              </span>
              <span className="text-sm tabular-nums text-ink-400 line-through">
                {oldPrice}
              </span>
            </div>

            <p className="mt-2 text-sm font-medium tabular-nums text-ink-700">
              {t("credit.credits", { count: pkg.credits.toLocaleString(numberLocale) })}
            </p>
            {typeof pkg.auto_thesis_runs === "number" && pkg.auto_thesis_runs > 0 && (
              <p className="mt-1 text-sm font-semibold text-primary-700">
                {tn("credit.thesesEquiv_one", "credit.thesesEquiv_other", pkg.auto_thesis_runs, {
                  label: formatRuns(pkg.auto_thesis_runs, numberLocale),
                })}
              </p>
            )}
            <p className="mt-0.5 text-xs tabular-nums text-ink-400">
              {t("credit.perK", { price: perThousand(pkg, showSepay) })}
            </p>
            {vsStarter > 0 && (
              <p className="mt-1 text-xs font-medium text-primary-700">
                {t("credit.cheaper", { pct: vsStarter })}
              </p>
            )}

            <div className="mt-auto flex flex-col gap-2 pt-6">
              <button
                type="button"
                onClick={() => polarBuy(pkg)}
                disabled={busy !== null}
                className="rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50 active:scale-[0.98]"
              >
                {busy === `polar:${pkg.id}` ? t("credit.payCardBusy") : t("credit.payCard")}
              </button>
              {showPayPal && (
                <button
                  type="button"
                  onClick={() => paypalBuy(pkg)}
                  disabled={busy !== null}
                  className="flex items-center justify-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50"
                >
                  <Wallet className="h-4 w-4" />
                  {busy === `paypal:${pkg.id}` ? t("credit.paypalBusy") : "PayPal"}
                </button>
              )}
              {showSepay && (
                <button
                  type="button"
                  onClick={() => sepayBuy(pkg)}
                  disabled={busy !== null}
                  className="flex items-center justify-center gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50"
                >
                  <Landmark className="h-4 w-4" />
                  {busy === `sepay:${pkg.id}` ? t("credit.sepayBusy") : t("credit.sepay")}
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
    {starter && (
      <p className="mt-3 text-xs text-ink-400">
        {t("credit.equivHint", { credits: starter.credits.toLocaleString(numberLocale) })}
      </p>
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
  const t = useLocale().t;
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
        <h3 className="text-base font-semibold text-ink-900">{t("credit.sepay.title")}</h3>
        <p className="mt-1 text-xs text-ink-500">{t("credit.sepay.hint")}</p>

        {paid ? (
          <div className="mt-6 rounded-xl bg-green-50 px-4 py-6 text-center text-green-700">
            {t("credit.sepay.paid")}
          </div>
        ) : (
          <>
            <div className="mt-4 flex justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={intent.qr_url} alt="SePay QR" className="h-56 w-56 rounded-lg border border-ink-100" />
            </div>
            <dl className="mt-4 space-y-1 text-sm">
              <Row label={t("credit.sepay.bank")} value={intent.bank_name || intent.bank_code} />
              <Row label={t("credit.sepay.account")} value={intent.account_number} />
              <Row label={t("credit.sepay.amount")} value={formatVnd(intent.amount_vnd)} />
              {/* transfer_content, not memo: on the shared VietinBank account
                  the routing prefix is part of what has to be typed. */}
              <Row label={t("credit.sepay.content")} value={intent.transfer_content} mono />
            </dl>
            <p className="mt-2 text-xs text-ink-500">
              {t("credit.sepay.keepCode", { code: intent.memo })}
            </p>
            <p className="mt-3 text-center text-xs text-ink-400">{t("credit.sepay.waiting")}</p>
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
