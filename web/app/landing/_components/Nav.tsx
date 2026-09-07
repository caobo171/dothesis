"use client";

import { useEffect, useState } from "react";

import { Button } from "./ds";
import { BrandLockup, CTA_HREF, CTA_PRIMARY, LOGIN_HREF } from "./shared";

// Anchors carry the /landing path because this Nav is also the blog shell's
// header: a bare "#features" is a dead link on /blog/vi/... and scrolls the
// landing page exactly the same way with the path in front.
const LINKS: Array<[string, string]> = [
  ["Features", "/landing#features"],
  ["Tools", "/landing#tools"],
  ["Pricing", "/landing#pricing"],
  ["FAQ", "/landing#faq"],
  // The only entry that leaves the marketing page. Kept last so the anchors
  // still read as one group.
  ["Blog", "/blog/vi"],
];

export function Nav() {
  // The bar only turns translucent once the page has actually moved; at rest it
  // is opaque white so the hero's indigo wash doesn't bleed through the logo.
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: scrolled ? "rgba(255,255,255,0.86)" : "#fff",
        backdropFilter: scrolled ? "saturate(180%) blur(10px)" : "none",
        borderBottom: "1px solid var(--ink-100)",
        transition: "background .2s",
      }}
    >
      <div
        className="lp-wrap"
        style={{
          height: 64,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <BrandLockup />
        <nav
          className="lp-nav-links"
          style={{ display: "flex", alignItems: "center", gap: 30 }}
        >
          {LINKS.map(([label, href]) => (
            <a key={label} href={href} className="lp-navlink">
              {label}
            </a>
          ))}
        </nav>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a
            href={LOGIN_HREF}
            className="lp-navlink"
            style={{ display: "inline-block" }}
          >
            Log in
          </a>
          <Button as="a" href={CTA_HREF} pill size="sm">
            {CTA_PRIMARY}
          </Button>
        </div>
      </div>
    </header>
  );
}
