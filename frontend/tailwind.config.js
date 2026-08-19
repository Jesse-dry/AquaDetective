/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 大屏深色科技风
        ink: '#0b1220',
        panel: '#111a2e',
        edge: '#1f2c4a',
        accent: '#38bdf8',
        ok: '#22c55e',
        warn: '#eab308',
        danger: '#ef4444',
      },
    },
  },
  plugins: [],
}
