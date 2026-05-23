import Link from "next/link";

type BrandProps = {
  collapsed?: boolean;
};

export function Brand({ collapsed = false }: BrandProps) {
  return (
    <Link href="/" className="flex items-center gap-3 no-underline">
      <div
        className="flex items-center justify-center rounded-xl bg-primary-600 text-white shadow-sm"
        style={{ width: 38, height: 38 }}
      >
        <svg width={22} height={22} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M19 4c-7 0-13 6-13 13v3h3c7 0 13-6 13-13V4Z" fill="white" fillOpacity={0.95} />
          <path d="M16 8 5 19" stroke="#1c2eff" strokeWidth={2} strokeLinecap="round" />
          <path d="M14 14H8" stroke="#1c2eff" strokeWidth={2} strokeLinecap="round" />
        </svg>
      </div>
      {!collapsed && (
        <div className="flex flex-col leading-tight">
          <span className="text-base font-extrabold tracking-tight text-ink-900">
            Do<span className="text-primary-600">Thesis</span>
          </span>
          <span className="text-[11px] font-medium text-ink-500">Draft with conviction</span>
        </div>
      )}
    </Link>
  );
}
