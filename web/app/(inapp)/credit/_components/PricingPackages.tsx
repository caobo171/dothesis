"use client";

import { Award, Minus, Plus, Ticket } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { apiFetch, swrFetcher } from "@/app/lib/api";
import type { CreditPackage } from "@/app/lib/credit-packages";

const PACKAGE_ICONS: Record<string, typeof Award> = {
  starter_package: Ticket,
  standard_package: Award,
  expert_package: Award,
};

export function PricingPackages({ onSuccess }: { onSuccess?: () => void }) {
  const { data: packages, error } = useSWR<CreditPackage[]>("/credit/packages", swrFetcher);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (error) return <div className="text-red-700">Could not load packages.</div>;
  if (!packages) return <div className="text-ink-500">Loading…</div>;

  const adjust = (id: string, delta: number) =>
    setQty((p) => ({ ...p, [id]: Math.max(1, Math.min(99, (p[id] || 1) + delta)) }));

  async function buy(pkg: CreditPackage) {
    setBusy(pkg.id);
    setErr(null);
    try {
      const res = await apiFetch("/credit/checkout", {
        method: "POST",
        body: { package_id: pkg.id },
      });
      if (res?.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        setErr("Could not start checkout.");
      }
    } catch (e: any) {
      setErr(e?.message || "Checkout failed.");
    } finally {
      setBusy(null);
      onSuccess?.();
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
        const quantity = qty[pkg.id] || 1;
        const totalCents = pkg.price_cents * quantity;
        const totalCredits = pkg.credits * quantity;
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
              <span className="text-3xl font-extrabold text-ink-900">${(pkg.price_cents / 100).toFixed(0)}</span>
              <span className="text-sm text-ink-400 line-through">${(pkg.old_price_cents / 100).toFixed(0)}</span>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                className="rounded-md border border-ink-200 p-1 text-ink-500 hover:bg-ink-50"
                onClick={() => adjust(pkg.id, -1)}
                aria-label="Decrease quantity"
              >
                <Minus className="h-4 w-4" />
              </button>
              <span className="w-10 text-center text-sm font-medium text-ink-900">{quantity}</span>
              <button
                type="button"
                className="rounded-md border border-ink-200 p-1 text-ink-500 hover:bg-ink-50"
                onClick={() => adjust(pkg.id, 1)}
                aria-label="Increase quantity"
              >
                <Plus className="h-4 w-4" />
              </button>
              <span className="ml-auto text-xs text-ink-500">
                Total: ${(totalCents / 100).toFixed(0)} · {totalCredits.toLocaleString()} cr.
              </span>
            </div>

            <button
              type="button"
              onClick={() => buy(pkg)}
              disabled={busy !== null}
              className="mt-5 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
            >
              {busy === pkg.id ? "Starting checkout…" : "Buy"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
