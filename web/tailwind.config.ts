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
        sans: ["Manrope", "ui-sans-serif", "system-ui"],
        serif: ["Source Serif 4", "Georgia", "serif"],
        mono: ["JetBrains Mono", "ui-monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
