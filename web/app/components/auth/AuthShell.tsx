/**
 * The frame the sign-in and sign-up screens sit in: a form column on the left,
 * the product demo beside it once there is room.
 *
 * Both screens were a centred card on a grey field — correct, and completely
 * silent about what is on the other side of the password. This gives the empty
 * two thirds of a desktop viewport something to say.
 *
 * The panel is dropped below xl rather than stacked below the form. It is
 * supporting material, and on a phone the form is the whole job — plus
 * ProductMock runs an interval, and a login screen is no place to spend a
 * phone's battery on a demo nobody scrolled to.
 *
 * Dropped, not `display: none`: a hidden element is still mounted, and its
 * effects — the demo's step timer among them — still run. The width has to be
 * a real condition on rendering for the phone to actually save the work.
 */
"use client";

import * as React from "react";

import { AuthBrandInline } from "../layout/Brand";
import { AuthExplainer } from "./AuthExplainer";

/** The xl breakpoint, as a query — kept in step with the classes below. */
const WIDE = "(min-width: 1280px)";

/**
 * False on the server and on the first client paint, then correct. The panel
 * is decoration, so appearing a tick late costs nothing, and starting from
 * `false` is what keeps the markup identical across hydration.
 */
function useIsWide(): boolean {
  const [wide, setWide] = React.useState(false);

  React.useEffect(() => {
    const mq = window.matchMedia(WIDE);
    const apply = () => setWide(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  return wide;
}

type AuthShellProps = {
  /** Screen title — "Sign in", "Create your account". */
  title: string;
  /** The one supporting line under it. */
  subtitle?: React.ReactNode;
  children: React.ReactNode;
};

export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  const wide = useIsWide();

  return (
    <div className="flex min-h-screen bg-white">
      <div className="flex w-full flex-col px-6 py-8 xl:w-[560px] xl:flex-none xl:border-r xl:border-ink-200 xl:px-16">
        {/* The brand rides in the same 400px column as the form rather than
            against the padding edge. Otherwise it drifts left of the fields —
            by 16px inside the xl column, and by half the viewport below xl,
            where the panel is gone and the form centres in the full width. */}
        <div className="mx-auto w-full max-w-[400px]">
          <AuthBrandInline />
        </div>

        <div className="flex flex-1 flex-col justify-center py-10">
          <div className="mx-auto w-full max-w-[400px]">
            <h1 className="text-2xl font-bold tracking-tight text-ink-900">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-1.5 text-sm leading-relaxed text-ink-500">
                {subtitle}
              </p>
            ) : null}

            <div className="mt-7 space-y-5">{children}</div>
          </div>
        </div>
      </div>

      {/* Both gates on purpose. `wide` decides whether this mounts at all;
          `hidden xl:flex` is the CSS holding the same line, so a resize
          between the media change and React's next paint can't flash a
          half-width panel. */}
      {wide && (
        <div className="hidden flex-1 items-center justify-center bg-gradient-to-b from-primary-50 to-white px-12 xl:flex">
          <AuthExplainer />
        </div>
      )}
    </div>
  );
}
