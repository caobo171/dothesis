"use client";

import { CheckCircle, FileText, Hash, Mail, RotateCcw, ShieldCheck, ShoppingCart, Ticket, Timer } from "lucide-react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useLocale } from "@/app/lib/i18n/LocaleProvider";
import { useMe } from "@/app/lib/use-me";

import { PricingPackages } from "./PricingPackages";

type OrderRow = {
  id: string;
  status: string;
  created_at: string | null;
};

export default function Credit() {
  const me = useMe();
  const { t, locale } = useLocale();
  const numberLocale = locale === "vi" ? "vi-VN" : "en-US";
  const params = useSearchParams();
  const polarStatus = params.get("polar");

  const orders = useSWR<OrderRow[]>("/credit/orders", swrFetcher);
  const orderCount = orders.data?.length || 0;

  const papers = useSWR<unknown[]>("/papers/list", swrFetcher);
  const draftCount = papers.data?.length;  // undefined while loading

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-6xl mx-auto">
        {polarStatus === "success" && (
          <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
            <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
            <p className="text-sm text-green-800">{t("credit.paid")}</p>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 mb-8 py-3 border-b border-ink-100">
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
            <span className="text-sm font-semibold tabular-nums text-primary-600">
              {t("credit.balance", { count: (me.data?.credit ?? 0).toLocaleString(numberLocale) })}
            </span>
          </div>
        </div>

        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-ink-900">{t("credit.title")}</h2>
            <p className="mt-1 max-w-xl text-sm text-ink-500">{t("credit.subtitle")}</p>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded bg-blue-50 flex items-center justify-center">
                <FileText className="w-4 h-4 text-blue-600" />
              </div>
              <div>
                <span className="text-lg font-bold tabular-nums text-ink-900">
                  {draftCount === undefined ? "—" : draftCount}
                </span>
                <span className="text-xs text-ink-500 ml-1">{t("credit.theses")}</span>
              </div>
            </div>
            <div className="w-px h-6 bg-ink-200" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded bg-green-50 flex items-center justify-center">
                <ShoppingCart className="w-4 h-4 text-green-600" />
              </div>
              <div>
                <span className="text-lg font-bold tabular-nums text-ink-900">{orderCount}</span>
                <span className="text-xs text-ink-500 ml-1">{t("credit.orders")}</span>
              </div>
            </div>
          </div>
        </div>

        <PricingPackages onSuccess={() => me.mutate()} />

        <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TrustNote icon={ShieldCheck} text={t("credit.note.refund")} />
          <TrustNote icon={RotateCcw} text={t("credit.note.deduct")} />
          <TrustNote icon={Timer} text={t("credit.note.confirm")} />
        </div>
      </div>
    </section>
  );
}

function TrustNote({ icon: Icon, text }: { icon: typeof ShieldCheck; text: string }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-ink-100 bg-white px-4 py-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
      <p className="text-xs leading-relaxed text-ink-500">{text}</p>
    </div>
  );
}
