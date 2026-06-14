/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Legacy terminal tokens (used by unredesigned pages) ──
        bg: {
          primary: '#0a0a0a',
          secondary: '#0d0d0d',
          tertiary: '#111111',
          hover: '#161616',
        },
        border: {
          DEFAULT: '#1f521f',
          subtle: '#0f2d0f',
        },
        text: {
          primary: '#33ff00',
          secondary: '#22cc00',
          muted: '#1f521f',
        },
        accent: {
          blue: '#33ff00',
          green: '#33ff00',
          amber: '#ffb000',
          red: '#ff3333',
          violet: '#ffb000',
          cyan: '#00ffff',
        },
        // ── Material-TUI tokens (new design system) ──
        "primary": "#96ccff",
        "on-primary": "#003353",
        "primary-container": "#00a6ff",
        "secondary": "#5dff3b",
        "secondary-container": "#30e200",
        "on-secondary": "#063900",
        "on-secondary-container": "#0f5e00",
        "tertiary": "#ffba43",
        "tertiary-container": "#d49200",
        "on-tertiary-container": "#4b3100",
        "surface": "#131313",
        "surface-container-lowest": "#0e0e0e",
        "surface-container-low": "#1c1b1b",
        "surface-container": "#201f1f",
        "surface-container-high": "#2a2a2a",
        "surface-container-highest": "#353534",
        "surface-bright": "#3a3939",
        "on-surface": "#e5e2e1",
        "on-surface-variant": "#bec7d4",
        "outline": "#88929d",
        "outline-variant": "#3f4852",
        "error": "#ffb4ab",
        "on-error": "#690005",
        "terminal-error": "#FF3B30",
      },
      borderRadius: {
        none: '0px',
        sm: '0px',
        DEFAULT: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        '3xl': '0px',
        // 'full' intentionally omitted so rounded-full stays at 9999px (avatar circles)
      },
      fontFamily: {
        sans: ['JetBrains Mono', 'Fira Code', 'VT323', 'monospace'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'headline-lg': ['24px', { lineHeight: '32px', fontWeight: '700' }],
        'headline-md': ['20px', { lineHeight: '28px', fontWeight: '700' }],
        'body-lg':     ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'body-md':     ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'label-caps':  ['11px', { lineHeight: '16px', fontWeight: '800', letterSpacing: '0.1em' }],
        'code-sm':     ['12px', { lineHeight: '16px', fontWeight: '400' }],
      },
      animation: {
        'blink': 'blink 1s step-end infinite',
        'blink-fast': 'blink 0.5s step-end infinite',
        'fade-in': 'fadeIn 0.1s ease-out',
        'slide-in': 'slideIn 0.2s ease-out',
        'shimmer': 'shimmer 2s infinite linear',
        'pulseFast': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glitch': 'glitch 0.3s ease-in-out',
        'spin': 'spin 1s linear infinite',
        'scanline': 'scanline 8s linear infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateX(-4px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        glitch: {
          '0%': { transform: 'translate(0)' },
          '20%': { transform: 'translate(-2px, 1px)', filter: 'hue-rotate(90deg)' },
          '40%': { transform: 'translate(2px, -1px)' },
          '60%': { transform: 'translate(-1px, 2px)', filter: 'hue-rotate(-90deg)' },
          '80%': { transform: 'translate(1px, -1px)' },
          '100%': { transform: 'translate(0)' },
        },
        spin: {
          to: { transform: 'rotate(360deg)' },
        },
        scanline: {
          '0%':   { top: '-10%' },
          '100%': { top: '110%' },
        },
      },
      boxShadow: {
        'terminal': '0 0 10px rgba(51, 255, 0, 0.12)',
        'terminal-md': '0 0 20px rgba(51, 255, 0, 0.18)',
        'amber': '0 0 10px rgba(255, 176, 0, 0.2)',
        'none': 'none',
      },
    },
  },
  plugins: [],
}
