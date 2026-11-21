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
        // the 3D die spins itself (Die3D); the wrapper only drops it in and bounces it
        tumble: {
          '0%': { transform: 'translateY(-90px) scale(0.8)', opacity: '0' },
          '35%': { transform: 'translateY(6px) scale(1.02)', opacity: '1' },
          '55%': { transform: 'translateY(-22px)' },
          '72%': { transform: 'translateY(3px)' },
          '86%': { transform: 'translateY(-6px)' },
          '100%': { transform: 'none' },
        },
        'dice-reveal': {
          '0%': { opacity: '0', visibility: 'hidden', transform: 'translateY(6px)' },
          '100%': { opacity: '1', visibility: 'visible', transform: 'none' },
        },
        'crit-glow': {
          '0%, 100%': { filter: 'drop-shadow(0 0 0 rgba(242,207,98,0))' },
          '40%': { filter: 'drop-shadow(0 0 28px rgba(242,207,98,0.9))' },
        },
        'crit-shake': {
          '0%, 100%': { transform: 'none', filter: 'none' },
          '20%': { transform: 'translateX(-7px)', filter: 'drop-shadow(0 0 18px rgba(226,128,122,0.8))' },
          '40%': { transform: 'translateX(6px)' },
          '60%': { transform: 'translateX(-4px)' },
          '80%': { transform: 'translateX(2px)' },
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
        tumble: 'tumble 1s ease-out both',
        // delays match SETTLE_MS in Die3D: the text and crit effects start when the die lands
        'dice-reveal': 'dice-reveal 350ms ease-out 800ms both',
        'crit-glow': 'crit-glow 1.4s ease-in-out 800ms 2',
        'crit-shake': 'crit-shake 450ms ease-out 800ms',
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
