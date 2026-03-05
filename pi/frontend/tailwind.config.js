/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontSize: {
        // Tuned for Raspberry Pi 7-inch display (800x480), still scales up on larger displays.
        hero: 'clamp(2.1rem, 8vw, 5rem)',
        'hero-sub': 'clamp(1.6rem, 6vw, 3.5rem)',
        'kiosk-xl': 'clamp(1.1rem, 3.4vw, 2.2rem)',
        'kiosk-lg': 'clamp(0.95rem, 2.7vw, 1.6rem)',
        'kiosk-md': 'clamp(0.85rem, 2.1vw, 1.25rem)',
        'kiosk-sm': 'clamp(0.7rem, 1.7vw, 0.95rem)',
      },
      colors: {
        surface: {
          DEFAULT: '#0f172a',
          card: '#1e293b',
          raised: '#334155',
        },
        accent: {
          DEFAULT: '#06b6d4',
          hover: '#0891b2',
          glow: '#67e8f9',
        },
      },
      keyframes: {
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-12px)' },
          '40%': { transform: 'translateX(12px)' },
          '60%': { transform: 'translateX(-8px)' },
          '80%': { transform: 'translateX(8px)' },
        },
        pulse_slow: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        shake: 'shake 0.45s ease-in-out',
        'pulse-slow': 'pulse_slow 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
