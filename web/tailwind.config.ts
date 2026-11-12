import type { Config } from "tailwindcss";
import { amber, grass, iris, red, slate } from "@radix-ui/colors";

// Same Radix steps as the CSS tokens in app/globals.css, read from the same
// package. Utilities get hex rather than var(--…) so opacity modifiers
// (bg-ink-50/60, bg-primary-50/40) keep working under Tailwind v3.

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // shadcn semantic tokens (driven by CSS vars in globals.css) — used by
        // shadcn primitives and the base layer (bg-background, border-border…).
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
          50: red.red3,
          100: red.red4,
          500: red.red8,
          600: red.red9,
          700: red.red10,
          text: red.red11,
        },
        // Brand accent — kept as the indigo identity; DEFAULT/foreground added
        // so shadcn `bg-primary` / `text-primary-foreground` work too.
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          50:  iris.iris3,
          100: iris.iris4,
          500: iris.iris8,
          600: iris.iris9,  // the single permitted accent hue
          700: iris.iris10,
        },
        // `ink` retuned to a neutral zinc scale (shadcn neutral feel) — every
        // existing ink-* utility across the app shifts to crisp neutrals.
        // Radix slate. Two text steps, so text has three levels: 900/800/700
        // strong (12), 600/500 muted (11), 400 faint (10).
        ink: {
          50:  slate.slate2,
          100: slate.slate3,
          200: slate.slate6,
          300: slate.slate7,
          400: slate.slate10,
          500: slate.slate11,
          600: slate.slate11,
          700: slate.slate12,
          800: slate.slate12,
          900: slate.slate12,
        },
        moss: { bg: grass.grass3, border: grass.grass6, fg: grass.grass11, text: grass.grass12 },
        ochre: { bg: amber.amber3, border: amber.amber6, fg: amber.amber11, text: amber.amber12 },
        "surface-input": "var(--surface-input)",
      },
      // Chatwoot's weight scale. semibold/bold are re-pointed onto it so existing
      // classes land on 520/620. extrabold stays 800 (not crosssocial's 700):
      // the Source Serif display headings use it and load a real 800 master.
      fontWeight: {
        420: "420",
        440: "440",
        460: "460",
        520: "520",
        620: "620",
        semibold: "520",
        bold: "620",
        extrabold: "800",
      },
      borderRadius: {
        btn: "var(--radius-btn)",
        chip: "var(--radius-chip)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        // shadcn convention — variables come from next/font in app/layout.tsx,
        // with system-font fallbacks so anything rendered before the font
        // finishes loading still looks right.
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        serif: ["Source Serif 4", "Georgia", "serif"],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
