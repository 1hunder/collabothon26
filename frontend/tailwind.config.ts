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
        quest: {
          lapis: '#22305B',
          'lapis-deep': '#161F3D',
          verdigris: '#3E8A7E',
          'verdigris-light': '#6FB5A8',
          gilt: '#C9A227',
          wax: '#A8322D',
          'wax-light': '#E2807A',
          vellum: '#E8DCC2',
          'vellum-dim': '#B9AE96',
          soot: '#15121A',
        },
      },
      keyframes: {
        bob: { '50%': { transform: 'translateY(3px)' } },
        tumble: {
          '0%': { transform: 'translateY(-30px) rotate(0deg) scale(0.6)', opacity: '0' },
          '40%': { transform: 'translateY(10px) rotate(300deg) scale(1.05)', opacity: '1' },
          '70%': { transform: 'translateY(-4px) rotate(600deg) scale(0.98)' },
          '100%': { transform: 'none' },
        },
        summon: {
          '0%': { transform: 'translateY(40px) rotateY(0deg) scale(0.4)', opacity: '0' },
          '60%': { transform: 'translateY(-6px) rotateY(540deg) scale(1.08)', opacity: '1' },
          '100%': { transform: 'none', opacity: '1' },
        },
        'hotspot-pulse': {
          '0%': { boxShadow: '0 0 0 0 rgba(201,162,39,0.7)', borderColor: 'rgba(201,162,39,0.9)' },
          '100%': { boxShadow: '0 0 0 14px rgba(201,162,39,0)', borderColor: 'rgba(201,162,39,0)' },
        },
        'seal-press': {
          '0%': { transform: 'scale(2.2)', opacity: '0' },
          '60%': { transform: 'scale(0.9)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      animation: {
        'hotspot-pulse': 'hotspot-pulse 1.6s ease-out 3',
        'seal-press': 'seal-press 700ms ease-out forwards',
        bob: 'bob 1.4s ease-in-out infinite',
        tumble: 'tumble 1s cubic-bezier(0.3, 0.7, 0.2, 1) both',
        summon: 'summon 0.6s cubic-bezier(0.2, 0.8, 0.2, 1) both',
      },
      borderRadius: {
        card: '16px',
        pill: '9999px',
      },
      fontFamily: {
        sans: ['Gotham', 'Montserrat', 'sans-serif'],
        quest: ['Alegreya', 'serif'],
        'quest-sans': ['Alegreya Sans', 'sans-serif'],
        'quest-title': ['Pirata One', 'serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
