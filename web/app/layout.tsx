import "./globals.css";
import type { ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AuthProvider } from "./lib/auth-context";

// shadcn convention: load fonts via next/font (self-hosted, no FOUT) and
// expose them as CSS variables. tailwind.config.ts wires --font-sans /
// --font-mono into font-sans / font-mono utilities.
const fontSans = Inter({
  subsets: ["latin", "vietnamese"],
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
  width: 1440,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${fontSans.variable} ${fontMono.variable}`}>
      <body className="bg-white text-ink-900 font-sans antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
