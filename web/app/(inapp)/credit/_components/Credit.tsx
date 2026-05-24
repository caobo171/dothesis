"use client";

import { CheckCircle, FileText, Hash, Mail, ShoppingCart, Ticket } from "lucide-react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useMe } from "@/app/lib/use-me";

import { PricingPackages } from "./PricingPackages";

type OrderRow = {
  id: string;
  status: string;
  created_at: string | null;
};

export default function Credit() {
  const me = useMe();
  const params = useSearchParams();
  const polarStatus = params.get("polar");

  const orders = useSWR<OrderRow[]>("/credit/orders", swrFetcher);
  const orderCount = orders.data?.length || 0;

  const papers = useSWR<unknown[]>("/papers", swrFetcher);
  const draftCount = papers.data?.length;  // undefined while loading

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-5xl mx-auto">
        {polarStatus === "success" && (
          <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
            <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
            <p className="text-sm text-green-800">
              Payment successful! Your credits will be added shortly.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 py-3 border-b border-ink-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-primary-50 text-primary-600 flex items-center justify-center font-semibold">
              {(me.data?.username || me.data?.email || "?").charAt(0).toUpperCase()}
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center gap-0.5 sm:gap-3">
              <span className="text-sm font-medium text-ink-900">
                {me.data?.username || me.data?.email?.split("@")[0] || "—"}
              </span>
              <div className="flex items-center gap-3 text-xs text-ink-500">
                <span className="flex items-center gap-1"><Mail className="w-3 h-3" /> {me.data?.email || "—"}</span>
                <span className="flex items-center gap-1"><Hash className="w-3 h-3" /> {me.data?.id?.slice(0, 8) || "—"}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 bg-primary-50 rounded-full px-3 py-1.5">
            <Ticket className="w-4 h-4 text-primary-600" />
            <span className="text-sm font-semibold text-primary-600">
              {me.data?.credit?.toLocaleString() || 0} Credit
            </span>
          </div>
        </div>

        <div className="flex items-center gap-6 mb-6">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-blue-50 flex items-center justify-center">
              <FileText className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <span className="text-lg font-bold text-ink-900">
                {draftCount === undefined ? "—" : draftCount}
              </span>
              <span className="text-xs text-ink-500 ml-1">Drafts</span>
            </div>
          </div>
          <div className="w-px h-6 bg-ink-200" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-green-50 flex items-center justify-center">
              <ShoppingCart className="w-4 h-4 text-green-600" />
            </div>
            <div>
              <span className="text-lg font-bold text-ink-900">{orderCount}</span>
              <span className="text-xs text-ink-500 ml-1">Orders</span>
            </div>
          </div>
        </div>

        <div className="mb-3">
          <h2 className="text-base font-semibold text-ink-900">Buy Credit</h2>
        </div>

        <PricingPackages onSuccess={() => me.mutate()} />

        <div className="bg-ink-50 rounded-xl p-4 mt-6">
          <h3 className="text-sm font-semibold text-ink-900 mb-3">Important Notes</h3>
          <ul className="space-y-1.5 text-xs text-ink-500">
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>100% refund if the tool fails or your draft cannot be completed.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>Credits are deducted when a draft is started and automatically refunded on engine error.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>Payment is processed within 1–3 minutes after Polar confirms.</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
