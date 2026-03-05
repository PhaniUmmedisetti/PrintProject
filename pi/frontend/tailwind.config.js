/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontSize: {
        // Fluid sizes — readable from across the room
        'hero':  'clamp(4rem,   16vw, 13rem)',
        'hero-sub': 'clamp(3rem, 12vw, 10rem)',
        'kiosk-xl': 'clamp(2rem, 6vw,  5rem)',
        'kiosk-lg': 'clamp(1.5rem, 4vw, 3.5rem)',
        'kiosk-md': 'clamp(1.25rem, 3vw, 2.5rem)',
        'kiosk-sm': 'clamp(1rem, 2vw, 1.75rem)',
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
