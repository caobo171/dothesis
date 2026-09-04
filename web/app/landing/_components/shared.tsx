/**
 * Shared helpers + small icons for the DoThesis landing page.
 * Ported from the design project's `landing-shared.jsx`.
 */
"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef } from "react";
import type { CSSProperties, ReactNode } from "react";

/** The logo mark already ships in web/public — no new asset needed. */
export const LOGO = "/logo-mark.png";
export const CTA_PRIMARY = "Start your thesis";

/**
 * The design mocked both CTAs as in-page anchors (#start / #login). In the real
 * app those routes exist, so the marketing page points at them directly rather
 * than scrolling to a section that cannot sign anyone up.
 */
export const CTA_HREF = "/signup";
export const LOGIN_HREF = "/login";

// -- tiny functional icons, currentColor, matching the product's stroke weight --
export function IconCheck({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function IconX({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function IconArrow({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function IconPlus({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

/** Brand lockup — the mark is the canonical asset; wordmark is serif 800. */
export function BrandLockup({ light = false }: { light?: boolean }) {
  return (
    <Link
      href="#top"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 10,
        textDecoration: "none",
      }}
    >
      <Image
        src={LOGO}
        alt=""
        width={30}
        height={30}
        style={{ borderRadius: 8 }}
      />
      <span
        className="lp-serif"
        style={{
          fontWeight: 800,
          fontSize: 20,
          letterSpacing: "-0.02em",
          color: light ? "#fff" : "var(--ink-900)",
        }}
      >
        DoThesis
      </span>
    </Link>
  );
}

/** Section header block. */
export function SectionHead({
  eyebrow,
  title,
  sub,
  align = "center",
  dark = false,
  maxWidth = 640,
}: {
  eyebrow?: string;
  title: string;
  sub?: string;
  align?: "center" | "left";
  dark?: boolean;
  maxWidth?: number;
}) {
  const muted = dark ? "rgba(255,255,255,0.66)" : "var(--ink-500)";
  return (
    <div
      style={{
        maxWidth,
        margin: align === "center" ? "0 auto" : 0,
        textAlign: align,
      }}
    >
      {eyebrow && (
        <div
          className="lp-eyebrow"
          style={{
            color: dark ? "rgba(255,255,255,0.5)" : "var(--primary-600)",
            marginBottom: 16,
          }}
        >
          {eyebrow}
        </div>
      )}
      <h2
        className="lp-display"
        style={{
          // jenni section H2: Inter Medium, 32px, 1.2 line-height, balanced.
          fontSize: "clamp(26px,3.2vw,32px)",
          lineHeight: 1.2,
          color: dark ? "#fff" : "var(--ink-900)",
        }}
      >
        {title}
      </h2>
      {sub && (
        <p className="lp-lead" style={{ color: muted, marginTop: 18 }}>
          {sub}
        </p>
      )}
    </div>
  );
}

/**
 * Scroll reveal wrapper. Adds `.lp-in` the first time the element crosses into
 * view, then stops observing — the reveal is one-shot, not a scroll-linked
 * effect. Browsers without IntersectionObserver (and anyone on reduced motion,
 * handled in CSS) just see the content.
 */
export function Reveal({
  children,
  delay = 0,
  style,
}: {
  children: ReactNode;
  delay?: number;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      el.classList.add("lp-in");
      return;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            timer = setTimeout(() => el.classList.add("lp-in"), delay);
            io.unobserve(el);
          }
        });
      },
      { threshold: 0.12 },
    );
    io.observe(el);
    return () => {
      if (timer) clearTimeout(timer);
      io.disconnect();
    };
  }, [delay]);

  return (
    <div ref={ref} className="lp-fade-up" style={style}>
      {children}
    </div>
  );
}
