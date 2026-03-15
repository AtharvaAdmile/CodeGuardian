/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0B1121',
          secondary: '#131C33',
          tertiary: '#1A2340',
          hover: '#1E2D4A',
        },
        border: {
          DEFAULT: '#1E2D4A',
          subtle: '#162033',
        },
        text: {
          primary: '#E2E8F0',
          secondary: '#94A3B8',
          muted: '#64748B',
        },
        accent: {
          blue: '#3B82F6',
          green: '#10B981',
          amber: '#F59E0B',
          red: '#EF4444',
          violet: '#8B5CF6',
          cyan: '#06B6D4',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'blink': 'blink 1s step-end infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
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
          '0%': { transform: 'translateX(-10px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
