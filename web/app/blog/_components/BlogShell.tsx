/**
 * Page chrome for every blog route.
 *
 * Reuses the landing page's Nav and Footer inside its `.lp-root` scope so the
 * blog is visibly the same product as the marketing site. The alternative —
 * a blog-only header — would have been faster and would have made the one
 * surface Google sends strangers to look like somebody else's website.
 *
 * Importing landing.css here rather than in each route keeps the token scope
 * and the `.lp-root` wrapper in the same file: they only work together.
 */
import type { ReactNode } from "react";

import "../../landing/landing.css";
import "../blog.css";

import { Footer } from "../../landing/_components/Footer";
import { Nav } from "../../landing/_components/Nav";

export function BlogShell({ children }: { children: ReactNode }) {
  return (
    <div className="lp-root">
      <Nav />
      <main className="blog-page">{children}</main>
      <Footer />
    </div>
  );
}
