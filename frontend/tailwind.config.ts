import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { yellow: '#FFD700', yellowHover: '#FFC700' },
        petrol: { DEFAULT: '#002E3C', muted: '#506C74' },
        warm: '#F1EFED',
        line: '#CED8DA',
        demo: '#6B21A8',
      },
      borderRadius: {
        card: '16px',
        pill: '9999px',
      },
      fontFamily: {
        sans: ['Gotham', 'Montserrat', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
