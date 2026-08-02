import Link from "next/link";

// The mark is the shared quill-and-book icon from the Survify brand family
// (copied out of .design-spec/project/assets/survify-logo-short.png), not the
// hand-drawn SVG that used to live here — DoThesis and Survify are sibling
// products and read as one house. Only the icon is shared; the wordmark stays
// "DoThesis" so the two products are never confused for each other.
const MARK_SRC = "/logo-mark.png";

type BrandProps = {
  collapsed?: boolean;
};

export function Brand({ collapsed = false }: BrandProps) {
  return (
    <Link href="/" className="flex items-center gap-3 no-underline">
      <img
        src={MARK_SRC}
        alt=""
        aria-hidden="true"
        className="rounded-lg"
        width={38}
        height={38}
      />
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
      <img src={MARK_SRC} alt="" aria-hidden="true" className="rounded-xl" width={48} height={48} />
      <div className="font-extrabold text-2xl text-ink-900">
        Do<span className="text-primary-600">Thesis</span>
      </div>
    </div>
  );
}
