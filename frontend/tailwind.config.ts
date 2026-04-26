import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0022FF',
        'primary-dark': '#001ACC',
        purple: '#6633FF',
        success: '#00B383',
        warn: '#E89C2C',
        error: '#E84C5A',
        ink: '#0A0E27',
        'ink-soft': '#3F4566',
        'ink-muted': '#8B91A8',
        rule: '#ECEDF3',
        'rule-strong': '#D8DAE5',
        'bg-soft': '#F7F8FC',
        'bg-blue': '#F0F3FF',
        'bg-purple': '#F4F0FF',
      },
      fontFamily: {
        serif: ['Instrument Serif', 'Georgia', 'serif'],
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
