import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  "#f1f3ff",
          100: "#e7eaff",
          500: "#3a4dff",
          600: "#1c2eff",
          700: "#0a1ee0",
        },
        ink: {
          50:  "#f5f6fb",
          100: "#eef0f6",
          200: "#e2e4ee",
          300: "#c2c5d6",
          400: "#8a8fa8",
          500: "#5b5f7d",
          700: "#292c44",
          800: "#161827",
          900: "#0b0d1a",
        },
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
