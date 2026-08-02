import Link from "next/link";

// The mark is the shared quill-and-book icon from the Survify brand family
// (copied out of .design-spec/project/assets/survify-logo-short.png), not the
// hand-drawn SVG that used to live here — DoThesis and Survify are sibling
// products and read as one house. Only the icon is shared; the wordmark stays
// "DoThesis" so the two products are never confused for each other.
const MARK_SRC = "/logo-mark.png";

/**
 * The logo mark on its own. Exported so no surface re-implements it — the chat
 * WorkflowSidebar used to hand-roll a gradient square with a letter "D", which
 * is exactly the drift the AuthBrand comment below warns about: when
 * logo-mark.png was replaced, every surface updated except that one.
 */
export function BrandMark({ size = 38, className = "rounded-lg" }: {
  size?: number;
  className?: string;
}) {
  return (
    <img
      src={MARK_SRC}
      alt=""
      aria-hidden="true"
      className={`shrink-0 ${className}`}
      width={size}
      height={size}
    />
  );
}

type BrandProps = {
  collapsed?: boolean;
};

export function Brand({ collapsed = false }: BrandProps) {
  return (
    <Link href="/" className="flex items-center gap-3 no-underline">
      <BrandMark size={38} />
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

// Centered mark-over-wordmark lockup for the auth screens (login, signup,
// verify, password reset). Those pages each hand-rolled the bare text wordmark;
// this gives them one lockup to share so the logo can never drift between them.
export function AuthBrand() {
  return (
    <div className="flex flex-col items-center gap-2">
      <BrandMark size={48} className="rounded-xl" />
      <div className="font-extrabold text-2xl text-ink-900">
        Do<span className="text-primary-600">Thesis</span>
      </div>
    </div>
  );
}
