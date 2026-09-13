"use client";

import { useT } from "@/app/lib/i18n/LocaleProvider";


export type ContextUsageSnapshot = {
  contextTokens: number;
  compactAtTokens: number;
};


export function formatContextTokens(value: number): string {
  const tokens = Math.max(0, Math.round(value));
  if (tokens < 1_000) return String(tokens);
  if (tokens < 1_000_000) {
    const thousands = tokens / 1_000;
    return `${Number(thousands.toFixed(thousands < 10 ? 1 : 0))}K`;
  }
  const millions = tokens / 1_000_000;
  return `${Number(millions.toFixed(1))}M`;
}


export function ContextUsageIndicator({
  contextUsage,
}: {
  contextUsage?: ContextUsageSnapshot | null;
}) {
  const t = useT();
  const used = Number(contextUsage?.contextTokens ?? 0);
  const threshold = Number(contextUsage?.compactAtTokens ?? 0);
  if (!Number.isFinite(used) || !Number.isFinite(threshold) || used <= 0 || threshold <= 0) {
    return null;
  }

  const remaining = Math.max(0, threshold - used);
  const percent = Math.min(100, Math.round((used / threshold) * 100));
  const label = remaining === 0
    ? t("chat.contextUsage.compacting", {
        used: formatContextTokens(used),
      })
    : t("chat.contextUsage.normal", {
        used: formatContextTokens(used),
        remaining: formatContextTokens(remaining),
        percent,
      });

  return (
    <span
      data-testid="context-usage"
      className="inline-flex items-center tabular-nums"
      title={t("chat.contextUsage.title")}
    >
      {label}
    </span>
  );
}
