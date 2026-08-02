import "./globals.css";
// KaTeX styles for math rendering in chat messages (remark-math + rehype-katex
// in MessageBubble). Loaded once at the root so every rendered equation is styled.
import "katex/dist/katex.min.css";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AuthProvider } from "./lib/auth-context";
import { LocaleProvider } from "./lib/i18n/LocaleProvider";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from "./lib/i18n/locale";

// shadcn convention: load fonts via next/font (self-hosted, no FOUT) and
// expose them as CSS variables. tailwind.config.ts wires --font-sans /
// --font-mono into font-sans / font-mono utilities.
//
// Sans is Inter: matching the neutral grotesque the category leaders (Jenni AI)
// use — tighter and more "product tool" than the rounded humanist Nunito Sans it
// replaces, and it still ships the `vietnamese` subset that is non-negotiable
// for this product. The --font-sans variable name is unchanged so Tailwind +
// every existing utility just pick it up.
const fontSans = Inter({
  subsets: ["latin", "latin-ext", "vietnamese"],
  variable: "--font-sans",
  display: "swap",
});

const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata = {
  title: "DoThesis — AI Thesis Agent",
  description:
    "Draft master's theses and PhD dissertations with 19 specialized AI agents and 100% verified citations.",
  icons: { icon: "/favicon.png" },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Read the locale SERVER-side from the cookie. This is what makes the whole
  // scheme hydration-safe: the server renders the same locale the client's first
  // render will use. Timezone detection (client-only) runs in LocaleProvider and
  // only when this cookie is absent — i.e. once per browser.
  const cookieStore = await cookies();
  const raw = cookieStore.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;

  return (
    <html lang={locale} className={`${fontSans.variable} ${fontMono.variable}`}>
      <body className="bg-white text-ink-900 font-sans antialiased">
        <LocaleProvider initialLocale={locale} hasCookie={isLocale(raw)}>
          <AuthProvider>{children}</AuthProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}
